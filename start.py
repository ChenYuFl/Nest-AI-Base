# main-beta0.7.py
# 说明：
# - 使用 subprocess.Popen 启动 Lm.py（使用指定的 Python 3.11 解释器）
# - 子进程以 -u 模式启动（无缓冲），并通过 stdin/stdout 通信
# - UI 上的字段（textEdit_6/textEdit_5/...）会传递给 Lm.py 的命令行参数
# - 需要把 PYTHON311_PATH 修改为本机 Python 3.11 可执行文件路径

import sys
import os
import yaml
import shutil
import requests
import res_rc
import subprocess
from PySide6.QtWidgets import (
    QApplication, QWidget, QFileDialog, QTableWidgetItem,
    QPushButton, QMessageBox, QHBoxLayout, QWidget as QW, QHeaderView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import Qt, QStringListModel, QThread, Signal, QTimer

# ========== 请在此处设置你本地的 Python 3.11 解释器路径 ==========
# Windows 示例: r"C:\Python311\python.exe"
# Linux 示例: "/usr/bin/python3.11"
PYTHON311_PATH = r"module/LM_load/DeepSeek/.venv/Scripts/python.exe"  # <-- <-- 这里改成你机器上的 Python 3.11 路径
# ==================================================================

# GGUF 查找目录（comboBox 列出此目录下的 .gguf 文件）
GGUF_DIR = os.path.abspath("download")

# ========== 子进程输出读取线程 ==========
class ProcessReaderThread(QThread):
    new_text = Signal(str)
    finished = Signal()

    def __init__(self, process):
        super().__init__()
        self.process = process
        self._running = True

    def run(self):
        try:
            # 持续读取 stdout
            while self._running and self.process and not self.process.stdout.closed:
                line = self.process.stdout.readline()
                if not line:
                    break
                try:
                    text = line.decode(errors="ignore")
                except AttributeError:
                    text = str(line)
                self.new_text.emit(text)
            # 读取剩下的 stderr (非阻塞方式)
            try:
                for line in self.process.stderr:
                    try:
                        text = line.decode(errors="ignore")
                    except Exception:
                        text = str(line)
                    self.new_text.emit(text)
            except Exception:
                pass
        finally:
            self.finished.emit()

    def stop(self):
        self._running = False
        self.wait(200)

# ========== 异步下载线程（你原来的） ==========
class DownloadThread(QThread):
    progress = Signal(int)
    message = Signal(str)
    finished = Signal(bool)

    def __init__(self, url, save_path):
        super().__init__()
        self.url = url
        self.save_path = save_path

    def run(self):
        try:
            self.message.emit(f"开始下载：{self.save_path}")
            with requests.get(self.url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("content-length", 0))
                chunk_size = 1024 * 50  # 每次读取50KB
                downloaded = 0

                with open(self.save_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size:
                                percent = int(downloaded * 100 / total_size)
                                self.progress.emit(percent)

            self.progress.emit(100)
            self.finished.emit(True)
            self.message.emit("下载完成！")
        except Exception as e:
            self.message.emit(f"下载出错：{e}")
            self.finished.emit(False)

# ==================== 主窗口 ====================
class OrgCeshi(QWidget):
    def __init__(self):
        super().__init__()

        # 加载 UI 文件
        loader = QUiLoader()
        self.ui = loader.load("./ui/index.ui")
        self.ui.show()
        self.ui.stackedWidget.setCurrentIndex(0)
        self.ui.tabWidget.setCurrentIndex(0)

        # ========= 绑定侧边导航 =========
        self.ui.pushButton.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(0))
        self.ui.pushButton_4.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(1))
        self.ui.pushButton_5.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(2))

        # ========= 功能按钮 =========
        self.ui.pushButton_11.clicked.connect(self.load_yml)
        if hasattr(self.ui, "pushButton_12"):
            self.ui.pushButton_12.clicked.connect(self.refresh_download_list)

        # ========= model process related =========
        self.model_process = None
        self.reader_thread = None
        self.model_running = False
        self.first_user_recorded = False

        # 绑定 UI 控件
        # comboBox 列出 gguf
        if hasattr(self.ui, "comboBox"):
            self.ui.comboBox.clear()
            self.refresh_gguf_list()
            # 当选择模型改变时不自动启动，但可以记录所选路径
            self.ui.comboBox.currentIndexChanged.connect(self.on_model_selected)

        # 启动模型按钮（pushButton_7）和 pushButton_9 同功能
        if hasattr(self.ui, "pushButton_7"):
            self.ui.pushButton_7.clicked.connect(self.toggle_start_model)
        if hasattr(self.ui, "pushButton_9"):
            self.ui.pushButton_9.clicked.connect(self.toggle_start_model)

        # 发送用户输入（pushButton_10）
        if hasattr(self.ui, "pushButton_10"):
            self.ui.pushButton_10.clicked.connect(self.send_user_input)

        # 启动时将默认值放到输入框中（映射到 Lm.py 参数）
        if hasattr(self.ui, "textEdit_6"):
            self.ui.textEdit_6.setPlainText("10240")  # MAX_TOKENS 默认
        if hasattr(self.ui, "textEdit_5"):
            self.ui.textEdit_5.setPlainText("8")      # CPU_THREADS 默认
        if hasattr(self.ui, "textEdit_4"):
            self.ui.textEdit_4.setPlainText("40960")  # N_CTX 默认
        if hasattr(self.ui, "textEdit_3"):
            self.ui.textEdit_3.setPlainText("你是一个乐于助人的AI助手，使用简洁清晰的语言回答问题。")

        # slider 与 spin box 联动 -> 用于 GPU_LAYERS
        if hasattr(self.ui, "horizontalSlider") and hasattr(self.ui, "spinBox"):
            self.ui.horizontalSlider.valueChanged.connect(self.ui.spinBox.setValue)
            self.ui.spinBox.valueChanged.connect(self.ui.horizontalSlider.setValue)

        # 初始化下载文件管理表格
        self.load_yml_list()
        self.refresh_download_list()

    # ============ 列出 GGUF 文件 ============
    def refresh_gguf_list(self):
        os.makedirs(GGUF_DIR, exist_ok=True)
        ggufs = [f for f in os.listdir(GGUF_DIR) if f.lower().endswith((".gguf", ".gguf"))]
        if hasattr(self.ui, "comboBox"):
            self.ui.comboBox.clear()
            if not ggufs:
                self.ui.comboBox.addItem("（无 .gguf 文件）")
            else:
                for name in ggufs:
                    self.ui.comboBox.addItem(name)

    def on_model_selected(self, index):
        # 当用户选择一个模型时，我们可以把路径显示到某个 textEdit（可选）
        if not hasattr(self.ui, "comboBox"):
            return
        name = self.ui.comboBox.currentText()
        if name and name != "（无 .gguf 文件）":
            model_path = os.path.join(GGUF_DIR, name)
            # 如果界面上有 textEdit_8 或类似控件可以显示 model path，写上去；否则不做事
            if hasattr(self.ui, "textEdit_8"):
                self.ui.textEdit_8.setPlainText(model_path)

    # ============ 启动或重启模型 ============
    def toggle_start_model(self):
        # 如果已运行则先重启
        if self.model_running:
            self.append_text("[系统] 模型正在重启...\n")
            self.stop_model()
            QTimer.singleShot(300, self.start_model)  # 延迟短暂时间再启动（确保端口/文件释放）
        else:
            self.start_model()
        self.first_user_recorded = False

    def start_model(self):
        # 构造命令行参数（从 UI 获取）
        if not os.path.exists(PYTHON311_PATH):
            QMessageBox.critical(self, "错误", f"找不到 Python 3.11 解释器：{PYTHON311_PATH}\n请在脚本顶部修改 PYTHON311_PATH。")
            return

        # 获取 model path
        model_path = None
        if hasattr(self.ui, "comboBox"):
            name = self.ui.comboBox.currentText()
            if name and name != "（无 .gguf 文件）":
                model_path = os.path.join(GGUF_DIR, name)

        if not model_path or not os.path.exists(model_path):
            QMessageBox.warning(self, "提示", "请选择有效的 .gguf 模型文件（在下载目录）。")
            return

        # 参数值获取与验证
        try:
            max_tokens = int(self.ui.textEdit_6.toPlainText().strip() or "10240")
        except Exception:
            max_tokens = 10240
        try:
            cpu_threads = int(self.ui.textEdit_5.toPlainText().strip() or "8")
        except Exception:
            cpu_threads = 8
        try:
            n_ctx = int(self.ui.textEdit_4.toPlainText().strip() or "40960")
        except Exception:
            n_ctx = 40960
        try:
            gpu_layers = int(self.ui.spinBox.value()) if hasattr(self.ui, "spinBox") else -1
        except Exception:
            gpu_layers = -1
        system_prompt = self.ui.textEdit_3.toPlainText().strip() if hasattr(self.ui, "textEdit_3") else "你是一个乐于助人的AI助手，使用简洁清晰的语言回答问题。"

        lm_script = os.path.abspath("module/LM_load/DeepSeek/Lm.py")
        if not os.path.exists(lm_script):
            QMessageBox.critical(self, "错误", f"找不到 Lm.py：{lm_script}")
            return

        cmd = [
            PYTHON311_PATH,
            "-u",  # unbuffered 输出，确保实时
            lm_script,
            "--model_path", model_path,
            "--max_tokens", str(max_tokens),
            "--cpu_threads", str(cpu_threads),
            "--gpu_layers", str(gpu_layers),
            "--n_ctx", str(n_ctx),
            "--system_prompt", system_prompt
        ]

        try:
            # 启动子进程（带 stdin/stdout/stderr）
            self.model_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0  # 直接使用 -u 保证无缓冲
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动模型子进程失败：{e}")
            return

        # 启动 stdout 读取线程
        self.reader_thread = ProcessReaderThread(self.model_process)
        self.reader_thread.new_text.connect(self.append_text)
        self.reader_thread.finished.connect(self.on_process_finished)
        self.reader_thread.start()

        self.model_running = True
        self.append_text(f"[系统] 模型进程已启动，PID={self.model_process.pid}\n")
        self.first_user_recorded = False

    def stop_model(self):
        if self.model_process:
            try:
                # 尝试优雅退出
                if self.model_process.stdin and not self.model_process.stdin.closed:
                    try:
                        self.model_process.stdin.write(b"exit\n")
                        self.model_process.stdin.flush()
                    except Exception:
                        pass
                # 等待一小会儿
                self.model_process.terminate()
            except Exception:
                pass
            try:
                self.model_process.kill()
            except Exception:
                pass

            # 停止 reader 线程
            if self.reader_thread:
                self.reader_thread.stop()
                self.reader_thread = None

            self.model_process = None
            self.model_running = False
            self.append_text("[系统] 模型进程已停止。\n")

    def on_process_finished(self):
        # 子进程输出读取线程结束（可能是进程退出）
        self.model_running = False
        self.append_text("[系统] 模型子进程输出已结束。\n")

    # ============ 发送用户输入给 Lm.py ============
    def send_user_input(self):
        if not self.model_running or not self.model_process:
            QMessageBox.warning(self, "提示", "模型尚未运行，请先启动模型（pushButton_7）。")
            return

        if not hasattr(self.ui, "textEdit_2"):
            return

        user_text = self.ui.textEdit_2.toPlainText().strip()
        if not user_text:
            return

        # 记录第一句话到 undoView
        if not self.first_user_recorded and hasattr(self.ui, "undoView"):
            try:
                # 假设 undoView 支持 append 操作（如 QTextEdit/QListWidget 等）
                # 这里尝试一些常见方法
                if hasattr(self.ui.undoView, "append"):
                    self.ui.undoView.append(user_text)
                elif hasattr(self.ui.undoView, "addItem"):
                    self.ui.undoView.addItem(user_text)
                else:
                    # fallback: 设置纯文本（如果控件是 QTextEdit）
                    try:
                        cur = self.ui.undoView.toPlainText()
                        self.ui.undoView.setPlainText(cur + "\n" + user_text)
                    except Exception:
                        pass
                self.first_user_recorded = True
            except Exception:
                pass

        # 将用户输入写入子进程 stdin
        try:
            to_send = (user_text + "\n").encode()
            self.model_process.stdin.write(to_send)
            self.model_process.stdin.flush()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"发送到模型失败：{e}")
            # 可能进程已退出
            self.model_running = False

        # 清空输入框（可根据需求不清空）
        self.ui.textEdit_2.clear()

    # ============ 将子进程输出追加到 textEdit ============
    def append_text(self, text):
        try:
            if hasattr(self.ui, "textEdit"):
                # 检测特殊标识（Lm.py 输出的分段标志）
                if "===RESPONSE-BEGIN===" in text:
                    self.ui.textEdit.append("\n[AI 回复开始]\n")
                    return
                elif "===RESPONSE-END===" in text:
                    self.ui.textEdit.append("\n[AI 回复结束]\n")
                    return

                # 普通输出直接追加
                self.ui.textEdit.append(text.strip())

                # 自动滚动到底部
                try:
                    cursor = self.ui.textEdit.textCursor()
                    cursor.movePosition(cursor.End)
                    self.ui.textEdit.setTextCursor(cursor)
                except Exception:
                    pass
        except Exception:
            pass

    # ============ 其余原来 YML/下载管理代码 ============
    def load_yml_list(self):
        yml_dir = r"D:\aibuild\org\yml"
        os.makedirs(yml_dir, exist_ok=True)
        files = [f for f in os.listdir(yml_dir) if f.endswith((".yml", ".yaml"))]

        model = QStringListModel(files)
        self.ui.listView.setModel(model)
        self.ui.listView.clicked.connect(
            lambda index: self.load_yml_file(os.path.join(yml_dir, files[index.row()]))
        )

    def load_yml(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择YAML文件", "", "YAML Files (*.yml *.yaml)")
        if file_path:
            self.load_yml_file(file_path)

    def load_yml_file(self, file_path):
        self.ui.textEdit_7.setPlainText(file_path)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法读取 YAML 文件：{e}")
            return

        if not isinstance(data, dict):
            QMessageBox.warning(self, "提示", "YAML 文件格式不正确，应为键值对结构。")
            return

        table = self.ui.tableWidget
        table.setRowCount(0)

        for key, value in data.items():
            row = table.rowCount()
            table.insertRow(row)

            name = value.get("name", "")
            intro = value.get("introduction", "")
            url = value.get("url", "")
            d_name = value.get("d_name", "")

            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(intro))
            table.setItem(row, 2, QTableWidgetItem(url))

            btn = QPushButton("下载")
            btn.clicked.connect(lambda _, u=url, n=d_name: self.start_download(u, n))
            table.setCellWidget(row, 3, btn)

        # 记录当前YML路径
        self.current_yml = file_path
        with open("last_yml.txt", "w", encoding="utf-8") as f:
            f.write(file_path)

    def start_download(self, url, d_name):
        if not url:
            QMessageBox.warning(self, "提示", "无效的下载地址！")
            return

        save_dir = "download"
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, d_name)

        QMessageBox.information(self, "提示", f"开始下载：{d_name}\n\nURL: {url}")

        self.download_thread = DownloadThread(url, save_path)
        self.download_thread.progress.connect(self.update_progress)
        # self.download_thread.message.connect(self.show_message)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.start()

    def update_progress(self, percent):
        self.ui.progressBar_2.setValue(percent)

    def download_finished(self, success):
        self.ui.progressBar_2.setValue(0)
        if success:
            QMessageBox.information(self, "下载完成", "文件已成功下载！")
            self.refresh_download_list()
            self.refresh_gguf_list()
        else:
            QMessageBox.warning(self, "下载失败", "下载过程中出现错误。")

    def refresh_download_list(self):
        table = self.ui.tableWidget_2
        download_dir = "download"
        os.makedirs(download_dir, exist_ok=True)
        table.setRowCount(0)

        yml_file = getattr(self, "current_yml", None)
        if not yml_file or not os.path.exists(yml_file):
            return

        with open(yml_file, "r", encoding="utf-8") as f:
            yml_data = yaml.safe_load(f) or {}

        for key, info in yml_data.items():
            d_name = info.get("d_name")
            intro = info.get("introduction", "无简介")
            name = info.get("name", key)
            file_path = os.path.join(download_dir, d_name)

            if os.path.exists(file_path):
                self.add_table2_row(name, intro, d_name, file_path)

    def add_table2_row(self, name, intro, d_name, path):
        table = self.ui.tableWidget_2
        row = table.rowCount()
        table.insertRow(row)

        table.setItem(row, 0, QTableWidgetItem(name))
        table.setItem(row, 1, QTableWidgetItem(intro))
        table.setItem(row, 2, QTableWidgetItem(path))

        browse_btn = QPushButton("浏览")
        delete_btn = QPushButton("删除")

        browse_btn.clicked.connect(lambda: self.open_folder(path))
        delete_btn.clicked.connect(lambda: self.delete_file(row, path))

        layout = QHBoxLayout()
        layout.addWidget(browse_btn)
        layout.addWidget(delete_btn)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cell_widget = QW()
        cell_widget.setLayout(layout)
        table.setCellWidget(row, 3, cell_widget)

        # 自动调整列宽以适应内容
        table.resizeColumnsToContents()

        # 让表格宽度撑满整个区域（最后一列自动拉伸）
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

    def open_folder(self, path):
        folder = os.path.dirname(path)
        if os.path.exists(folder):
            os.startfile(os.path.abspath(folder))
        else:
            QMessageBox.warning(self, "提示", f"文件夹不存在：{folder}")

    def delete_file(self, row, path):
        if not os.path.exists(path):
            QMessageBox.warning(self, "提示", "文件不存在。")
            return

        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除此文件吗？\n{path}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                os.remove(path)
                self.ui.tableWidget_2.removeRow(row)
                QMessageBox.information(self, "成功", "文件已删除。")
                self.refresh_gguf_list()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败：{e}")

# ==================== 程序入口 ====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OrgCeshi()
    sys.exit(app.exec())
