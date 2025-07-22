#!/usr/bin/env python3

import sys
import subprocess
import json
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QTextEdit, QMessageBox, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal as Signal, QSize, QRect
from PyQt5.QtGui import QFont, QGuiApplication, QPixmap, QMovie, QIcon
from PyQt5 import QtCore

# Genel ikon boyutu sabitlerini tanımla (yeni dikdörtgen boyutlar)
ICON_TARGET_WIDTH = 47  # Piksel cinsinden
ICON_TARGET_HEIGHT = 100 # Piksel cinsinden

class F3Worker(QThread):
    """
    f3 komutlarını ayrı bir thread'de çalıştırmak için Worker sınıfı.
    GUI'nin donmasını engeller.
    Bu sürüm sadece f3probe komutunu çalıştırır.
    """
    finished = Signal(str)
    progress = Signal(str)
    error = Signal(str)
    f3probe_result = Signal(str, str, str, str)

    def __init__(self, disk_path, translations, current_language_index):
        super().__init__()
        self.disk_path = disk_path
        self.command = "f3probe"
        self._translations = translations
        self._current_language_index = current_language_index

    def tr(self, key):
        """Worker içinde kullanılacak çeviri fonksiyonu."""
        lang_key = "tr" if self._current_language_index == 0 else "en"
        return self._translations.get(lang_key, {}).get(key, key)

    def run(self):
        try:
            f3_executable = "pkexec f3"

            full_command_str = f"{f3_executable}probe {self.disk_path}"
            self.progress.emit(self.tr("test_start_message") + f" {self.disk_path}\n")
            print(f"DEBUG (TERMINAL): Test başlatılıyor komut: {full_command_str}") # YENİ DEBUG

            import shlex
            command_list = shlex.split(full_command_str)

            process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            stdout_lines = []
            stderr_lines = []

            for line in process.stdout:
                stdout_lines.append(line.strip())
                self.progress.emit(line)
                print(f"DEBUG (TERMINAL - f3probe stdout): {line.strip()}") # YENİ DEBUG

            for line in process.stderr:
                stderr_lines.append(line.strip())
                self.error.emit(line)
                print(f"DEBUG (TERMINAL - f3probe stderr): {line.strip()}") # YENİ DEBUG

            process.wait()

            if process.returncode == 0 or process.returncode == 102:
                self.finished.emit(self.tr("command_success"))
                self._parse_f3probe_output(stdout_lines)
                if process.returncode == 102:
                    self.finished.emit(self.tr("fake_device_detected_code_102"))
            else:
                error_output = "\n".join(stderr_lines) if stderr_lines else self.tr("no_output_found")
                if "polkit" in error_output.lower() or "authentication" in error_output.lower():
                    self.error.emit(self.tr("authentication_error").format(detail=error_output))
                elif "not found" in error_output.lower() and "pkexec" in error_output.lower():
                     self.error.emit(self.tr("pkexec_not_found"))
                else:
                    self.error.emit(self.tr("command_error_code") + f": {process.returncode}\nDetay: {error_output}")

        except FileNotFoundError:
            self.error.emit(self.tr("f3_not_found_error"))
            print(f"DEBUG (TERMINAL): FileNotFoundError: {self.tr('f3_not_found_error')}") # YENİ DEBUG
        except Exception as e:
            self.error.emit(self.tr("unexpected_error") + f": {e}")
            print(f"DEBUG (TERMINAL): Unexpected error in F3Worker: {e}") # YENİ DEBUG

    def _parse_f3probe_output(self, lines):
        """f3probe çıktısını ayrıştırır ve ilgili bilgileri yayar."""
        real_capacity = self.tr("not_detected")
        promised_capacity = self.tr("not_detected")
        brand_model = self.tr("not_detected") # Bu, f3probe çıktısından gelmez, yalnızca bir yer tutucu
        status_message = self.tr("test_completed")

        is_fake = False

        for line in lines:
            if "Good news: The device" in line and "is the real thing" in line:
                status_message = self.tr("probably_genuine")
            elif "Bad news: The device" in line and "is a counterfeit" in line:
                is_fake = True
                status_message = self.tr("fake_warning")
            elif "WARNING: Only" in line and "sectors were found" in line:
                is_fake = True
                try:
                    parts = line.split("Only ")[1].split(" of ")
                    real_sectors = int(parts[0].replace(",", "").strip()) if len(parts) > 0 else 0
                    declared_sectors = int(parts[1].split(" sectors")[0].replace(",", "").strip()) if len(parts) > 1 else 0

                    sector_size_bytes = 512

                    real_capacity_gb = round(real_sectors * sector_size_bytes / (1024**3), 2)
                    declared_capacity_gb = round(declared_sectors * sector_size_bytes / (1024**3), 2)

                    real_capacity = f"{real_capacity_gb} GB"
                    promised_capacity = f"{declared_capacity_gb} GB"
                except (ValueError, IndexError):
                    self.error.emit(self.tr("f3probe_capacity_parse_error"))

            elif "*Usable* size:" in line:
                try:
                    size_part = line.split(":")[-1].strip().split("(")[0].strip()
                    real_capacity = size_part
                except IndexError:
                    pass
            elif "Announced size:" in line:
                try:
                    size_part = line.split(":")[-1].strip().split("(")[0].strip()
                    promised_capacity = size_part
                except IndexError:
                    pass

        # is_fake bayrağına göre nihai durumu ayarla
        if is_fake:
            status_message = self.tr("fake_warning")
        elif real_capacity != self.tr("not_detected") and promised_capacity != self.tr("not_detected"):
            # Düzeltme: Burada kesilen satırı tamamladık
            try:
                real_val, real_unit = real_capacity.split(" ")
                promised_val, promised_unit = promised_capacity.split(" ")

                if float(real_val) != float(promised_val) or real_unit != promised_unit:
                    status_message = self.tr("capacity_mismatch_warning")
                else:
                     status_message = self.tr("probably_genuine")
            except (ValueError, IndexError):
                if real_capacity != promised_capacity:
                    status_message = self.tr("capacity_mismatch_warning")
                else:
                    status_message = self.tr("probably_genuine")

        self.f3probe_result.emit(real_capacity, promised_capacity, brand_model, status_message)


class FakeUSBTesterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fake USB Tester")
        self.current_language_index = 0  # 0: Türkçe, 1: English
        self.translations = self._load_translations()
        self.icon_paths = {}  # İkon yollarını saklamak için sözlük
        self.status_text_edit = QTextEdit()  # _load_icon_paths'tan önce tanımlanmalı
        self._load_icon_paths()
        self._load_and_set_window_icon()  # Pencere ikonunu ayarla
        self.init_ui()

        # DÜZELTME: Sinyal bağlantısını diskler yüklenmeden önce yap.
        self.flash_drive_combo.currentIndexChanged.connect(self._on_disk_selected)
        print("DEBUG (TERMINAL): currentIndexChanged sinyali bağlandı.")

        self._load_disks() # Diskler yüklendiğinde _on_disk_selected tetiklenecektir.
        self.update_ui_language()
        self._set_initial_icon()  # Başlangıç ikonu

        self.is_processing = False


        self.setMinimumWidth(350)

    def _load_icon_paths(self):
        """İkon dosyalarının yollarını bulur ve saklar."""
        icons = ["flashicon.png", "flashicon_scanning.gif", "flashicon_testOK.png", "flashicon_testFAIL.png"]
        for icon in icons:
            path = self._find_icon_path(icon)
            if path:
                self.icon_paths.update({icon: path})
            else:
                self.status_text_edit.append(self.tr("icon_load_error").format(path=icon))
                print(f"DEBUG (TERMINAL): İkon yüklenemedi: {icon}") # YENİ DEBUG

    def _load_and_set_window_icon(self):
        """Pencere ikonunu ayarlar."""
        icon_path = self.icon_paths.get("flashicon.png")
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

    def _load_translations(self):
        """Çoklu dil metinlerini yükler."""
        return {
            "tr": {
                "flash_drive_label": "Flaş Bellek:",
                "select_drive_placeholder": "Lütfen bir disk seçin...",
                "brand_model_label": "Marka/Model:",
                "promised_capacity_label": "Vaadedilen Kapasite:",
                "real_capacity_label": "Gerçek Kapasite:",
                "not_tested": "Test edilmedi.",
                "not_detected": "Tespit edilemedi.",
                "status_label": "Durum:",
                "initial_status": "Lütfen bir test başlatın.",
                "start_test_button": "Testi Başlat",
                "language_button": "Language",
                "about_button": "Hakkında",
                "about_title": "Hakkında",
                "about_text": "Bu uygulama f3 (Fight Flash Fraud) aracını kullanarak USB belleklerin gerçek kapasitesini test etmek için tasarlanmıştır.\n\nYapımcı: @Zeus \nVersiyon: 0.1 \nLisans: GNU GPLv3",
                "select_drive_warning_title": "Disk Seçim Uyarısı",
                "select_drive_warning_text": "Lütfen test etmek için bir flaş bellek seçiniz.",
                "yes_button": "Evet",
                "no_button": "Hayır",
                "command_success": "Komut başarıyla tamamlandı.",
                "command_error_code": "Komut hata kodu ile tamamlandı:",
                "f3_not_found_error": "Hata: 'pkexec' veya 'f3' komutları bulunamadı. Lütfen yüklü olduğundan ve PATH'inizde olduğundan emin olun.",
                "unexpected_error": "Beklenmeyen bir hata oluştu:",
                "processing_message": "İşlem devam ediyor, lütfen bekleyiniz...",
                "invalid_disk_selection": "Geçersiz disk seçimi.",
                "disk_loading_error": "Diskler yüklenirken hata oluştu:",
                "detected": "Tespit edildi.",
                "probably_genuine": "Bu flaş bellek muhtemelen gerçek.",
                "fake_warning": "UYARI: Bu flaş bellek sahte çıktı!",
                "real_capacity_info": "Gerçek Kapasite: {real_cap} (Vaadedilen: {promised_cap})",
                "parsing_error": "f3 çıktısı ayrıştırılamadı. Ham çıktı için Durum alanına bakınız.",
                "info_reset_message": "Disk bilgileri sıfırlandı.",
                "current_disk_info": "Mevcut Disk Bilgisi:",
                "capacity_mismatch_warning": "UYARI: Vaadedilen ve gerçek kapasite farklı!",
                "pkexec_not_found": "Hata: 'pkexec' komutu bulunamadı. Lütfen yüklü olduğundan emin olun (genellikle policykit-1 paketiyle gelir).",
                "authentication_error": "Yetkilendirme Hatası: 'f3' komutunu çalıştırmak için yetkiniz yok veya parola girilmedi.\nLütfen pkexec ve Polkit ayarlarını kontrol edin. Detay: {detail}",
                "test_start_message": "Test başlatılıyor:",
                "test_completed": "Test tamamlandı.",
                "f3probe_capacity_parse_error": "f3probe kapasite uyarısı ayrıştırılırken hata.",
                "no_output_found": "Çıktı yok.",
                "icon_load_error": "İkon yüklenemedi: {path}",
                "fake_device_detected_code_102": "Sahte cihaz tespit edildi (Hata Kodu 102)."
            },
            "en": {
                "flash_drive_label": "Flash Drive:",
                "select_drive_placeholder": "Please select a drive...",
                "brand_model_label": "Brand/Model:",
                "promised_capacity_label": "Promised Capacity:",
                "real_capacity_label": "Real Capacity:",
                "not_tested": "Not tested.",
                "not_detected": "Not detected.",
                "status_label": "Status:",
                "initial_status": "Please start a test.",
                "start_test_button": "Start Test",
                "language_button": "Language",
                "about_button": "About",
                "about_title": "About",
                "about_text": "This application is designed to test the real capacity of USB drives using the f3 (Fight Flash Fraud) tool.\n\nDeveloper: @Zeus \nVersion: 0.1 \nLicence: GNU GPLv3",
                "select_drive_warning_title": "Drive Selection Warning",
                "select_drive_warning_text": "Please select a flash drive to test.",
                "yes_button": "Yes",
                "no_button": "No",
                "command_success": "Command completed successfully.",
                "command_error_code": "Command completed with error code:",
                "f3_not_found_error": "Error: 'pkexec' or 'f3' commands not found. Please ensure they are installed and in your PATH.",
                "unexpected_error": "An unexpected error occurred:",
                "processing_message": "Processing, please wait...",
                "invalid_disk_selection": "Invalid disk selection.",
                "disk_loading_error": "Error loading disks:",
                "detected": "Detected.",
                "probably_genuine": "This flash drive is likely genuine.",
                "fake_warning": "WARNING: This flash drive is fake!",
                "real_capacity_info": "Real Capacity: {real_cap} (Promised: {promised_cap})",
                "parsing_error": "Failed to parse f3 output. See Status field for raw output.",
                "info_reset_message": "Disk information reset.",
                "current_disk_info": "Current Disk Information:",
                "capacity_mismatch_warning": "WARNING: Announced and real capacity differ!",
                "pkexec_not_found": "Error: 'pkexec' command not found. Please ensure it is installed (usually with policykit-1 package).",
                "authentication_error": "Authentication Error: You don't have permission or password was not entered to run 'f3' commands.\nPlease check pkexec and Polkit settings. Details: {detail}",
                "test_start_message": "Starting test:",
                "test_completed": "Test completed.",
                "f3probe_capacity_parse_error": "Error parsing f3probe capacity warning.",
                "no_output_found": "No output found.",
                "icon_load_error": "Could not load icon: {path}"
            }
        }

    def tr(self, key):
        """Mevcut dile göre metni döndürür."""
        lang_key = "tr" if self.current_language_index == 0 else "en"
        return self.translations.get(lang_key, {}).get(key, key)

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Flaş Bellek ve İkon Bölümü
        top_section_layout = QHBoxLayout()

        # Flaş Bellek Seçimi Sol Taraf
        flash_drive_selection_layout = QVBoxLayout()
        flash_drive_layout = QHBoxLayout()
        self.flash_drive_label = QLabel()
        self.flash_drive_label.setFont(QFont("Arial", 10))
        self.flash_drive_combo = QComboBox()
        self.flash_drive_combo.setPlaceholderText(self.tr("select_drive_placeholder"))
        self.flash_drive_combo.setFont(QFont("Arial", 10))
        flash_drive_layout.addWidget(self.flash_drive_label)
        flash_drive_layout.addWidget(self.flash_drive_combo)
        flash_drive_selection_layout.addLayout(flash_drive_layout)

        # Bilgi Alanları (sol tarafta kalacak)
        info_layout = QVBoxLayout()
        self.current_disk_info_label = QLabel()
        self.brand_model_label = QLabel()
        self.promised_capacity_label = QLabel()
        self.real_capacity_label = QLabel()

        self.current_disk_info_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.brand_model_label.setFont(QFont("Arial", 10))
        self.promised_capacity_label.setFont(QFont("Arial", 10))
        self.real_capacity_label.setFont(QFont("Arial", 10))

        info_layout.addWidget(self.current_disk_info_label)
        info_layout.addWidget(self.brand_model_label)
        info_layout.addWidget(self.promised_capacity_label)
        info_layout.addWidget(self.real_capacity_label)
        flash_drive_selection_layout.addLayout(info_layout)

        top_section_layout.addLayout(flash_drive_selection_layout)  # Sol tarafı ana yatay düzene ekle

        # İkon Alanı (sağ tarafa yanaşık)
        self.icon_label = QLabel()
        self.icon_label.setGeometry(QRect(60, 40, ICON_TARGET_WIDTH, ICON_TARGET_HEIGHT))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # İçeriği ortalamak için
        top_section_layout.addWidget(self.icon_label)
        top_section_layout.setAlignment(self.icon_label, Qt.AlignmentFlag.AlignRight)  # İkonu sağa yasla

        main_layout.addLayout(top_section_layout)  # En üstteki ana yatay düzeni ekle

        # Durum Alanı
        status_group_box = QFrame()
        status_group_box.setFrameShape(QFrame.Shape.StyledPanel)
        status_group_box.setFrameShadow(QFrame.Shadow.Sunken)
        status_layout = QVBoxLayout()

        self.status_title_label = QLabel()
        self.status_text_edit.setFont(QFont("Arial", 9))
        self.status_text_edit.setReadOnly(True)
        self.status_text_edit.setText(self.tr("initial_status"))

        status_layout.addWidget(self.status_title_label)
        status_layout.addWidget(self.status_text_edit)
        status_group_box.setLayout(status_layout)
        main_layout.addWidget(status_group_box)

        # Butonlar
        button_layout = QHBoxLayout()
        self.start_test_button = QPushButton()
        self.start_test_button.setFont(QFont("Arial", 10))
        self.start_test_button.clicked.connect(self._start_test)

        button_layout.addWidget(self.start_test_button)
        main_layout.addLayout(button_layout)

        # Yardımcı Butonlar
        utility_button_layout = QHBoxLayout()
        self.language_button = QPushButton("Language")
        self.about_button = QPushButton()

        self.language_button.setFont(QFont("Arial", 10))
        self.about_button.setFont(QFont("Arial", 10))

        self.language_button.clicked.connect(self._toggle_language)
        self.about_button.clicked.connect(self._show_about_dialog)

        utility_button_layout.addWidget(self.language_button)
        utility_button_layout.addWidget(self.about_button)
        main_layout.addLayout(utility_button_layout)

        self.setLayout(main_layout)

    def _find_icon_path(self, icon_name):
        """
        İkon dosyasını program dizininde veya /usr/share altında arar.
        """
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv else os.getcwd()
        program_dir_path = os.path.join(script_dir, icon_name)

        # Yerel dizin kontrolü
        if os.path.exists(program_dir_path):
            return program_dir_path

        # /usr/share dizini kontrolü
        share_dir_path = os.path.join("/usr", "share", "Fake_USB_Tester", "icons", icon_name)
        if os.path.exists(share_dir_path):
            return share_dir_path

        return None

    def _set_icon_to_label(self, icon_path):
        """Verilen yoldaki ikonu icon_label'a yükler ve ayarlar."""
        if icon_path:
            scaled_size = QSize(ICON_TARGET_WIDTH, ICON_TARGET_HEIGHT)

            if icon_path.lower().endswith(".gif"):
                if hasattr(self, '_current_movie') and self._current_movie is not None:
                    self._current_movie.stop()
                    self._current_movie = None

                movie = QMovie(icon_path)
                if movie.isValid():
                    self.icon_label.setScaledContents(True)
                    self.icon_label.setFixedSize(scaled_size)

                    # Bu satır şimdi aktiftir ve GIF'in pürüzsüzlüğünü sağlamalıdır.
                    movie.setScaledSize(scaled_size)

                    self.icon_label.setMovie(movie)
                    movie.start()
                    self._current_movie = movie
                    QApplication.processEvents()
                else:
                    self.status_text_edit.append(self.tr("icon_load_error").format(path=icon_path))
                    self.icon_label.clear()
            else:
                if hasattr(self, '_current_movie') and self._current_movie is not None:
                    self._current_movie.stop()
                    self._current_movie = None

                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(scaled_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.icon_label.setPixmap(scaled_pixmap)
                    self.icon_label.setFixedSize(scaled_size)
                    self.icon_label.setScaledContents(True)
                else:
                    self.status_text_edit.append(self.tr("icon_load_error").format(path=icon_path))
                    self.icon_label.clear()
        else: # Bu 'else' bloğu 'if icon_path:' bloğuna aittir ve şimdi doğru yerdedir.
            self.icon_label.clear()


    def _set_initial_icon(self):
        """Başlangıç ikonunu yükler ve ayarlar."""
        icon_path = self.icon_paths.get("flashicon.png")
        self._set_icon_to_label(icon_path)

    def update_ui_language(self):
        """Mevcut dile göre tüm UI elemanlarının metinlerini günceller."""
        self.flash_drive_label.setText(self.tr("flash_drive_label"))
        self.current_disk_info_label.setText(self.tr("current_disk_info"))

        current_brand_text = self.brand_model_label.text()
        current_promised_text = self.promised_capacity_label.text()
        current_real_text = self.real_capacity_label.text()

        tr_not_detected = self.translations.get("tr", {}).get("not_detected")
        en_not_detected = self.translations.get("en", {}).get("not_detected")

        tr_brand_label = self.translations.get("tr", {}).get("brand_model_label")
        en_brand_label = self.translations.get("en", {}).get("brand_model_label")

        if tr_not_detected in current_brand_text or en_not_detected in current_brand_text:
            self.brand_model_label.setText(f"{self.tr('brand_model_label')} {self.tr('not_detected')}")
        else:
            if current_brand_text.startswith(tr_brand_label) and len(current_brand_text.split(tr_brand_label)) > 1:
                value = current_brand_text.split(tr_brand_label)[1].strip()
                self.brand_model_label.setText(f"{self.tr('brand_model_label')} {value}")
            elif current_brand_text.startswith(en_brand_label) and len(current_brand_text.split(en_brand_label)) > 1:
                value = current_brand_text.split(en_brand_label)[1].strip()
                self.brand_model_label.setText(f"{self.tr('brand_model_label')} {value}")
            else:
                self.brand_model_label.setText(f"{self.tr('brand_model_label')} {self.tr('not_detected')}")


        tr_promised_label = self.translations.get("tr", {}).get("promised_capacity_label")
        en_promised_label = self.translations.get("en", {}).get("promised_capacity_label")

        if tr_not_detected in current_promised_text or en_not_detected in current_promised_text:
            self.promised_capacity_label.setText(f"{self.tr('promised_capacity_label')} {self.tr('not_detected')}")
        else:
            if current_promised_text.startswith(tr_promised_label) and len(current_promised_text.split(tr_promised_label)) > 1:
                value = current_promised_text.split(tr_promised_label)[1].strip()
                self.promised_capacity_label.setText(f"{self.tr('promised_capacity_label')} {value}")
            elif current_promised_text.startswith(en_promised_label) and len(current_promised_text.split(en_promised_label)) > 1:
                value = current_promised_text.split(en_promised_label)[1].strip()
                self.promised_capacity_label.setText(f"{self.tr('promised_capacity_label')} {value}")
            else:
                self.promised_capacity_label.setText(f"{self.tr('promised_capacity_label')} {self.tr('not_detected')}")


        tr_not_tested = self.translations.get("tr", {}).get("not_tested")
        en_not_tested = self.translations.get("en", {}).get("not_tested")

        tr_real_label = self.translations.get("tr", {}).get("real_capacity_label")
        en_real_label = self.translations.get("en", {}).get("real_capacity_label")

        if tr_not_tested in current_real_text or en_not_tested in current_real_text:
            self.real_capacity_label.setText(f"{self.tr('real_capacity_label')} {self.tr('not_tested')}")
        else:
            if current_real_text.startswith(tr_real_label) and len(current_real_text.split(tr_real_label)) > 1:
                value = current_real_text.split(tr_real_label)[1].strip()
                self.real_capacity_label.setText(f"{self.tr('real_capacity_label')} {value}")
            elif current_real_text.startswith(en_real_label) and len(current_real_text.split(en_real_label)) > 1:
                value = current_real_text.split(en_real_label)[1].strip()
                self.real_capacity_label.setText(f"{self.tr('real_capacity_label')} {value}")
            else:
                self.real_capacity_label.setText(f"{self.tr('real_capacity_label')} {self.tr('not_tested')}")


        self.status_title_label.setText(self.tr("status_label"))
        current_status_text = self.status_text_edit.toPlainText()

        # DÜZELTME: Tanımlanmayan değişkenler yerine doğrudan çevirileri kullan
        tr_initial_status = self.translations.get("tr", {}).get("initial_status")
        en_initial_status = self.translations.get("en", {}).get("initial_status")
        tr_info_reset_message = self.translations.get("tr", {}).get("info_reset_message")
        en_info_reset_message = self.translations.get("en", {}).get("info_reset_message")

        if current_status_text == tr_initial_status or \
           current_status_text == en_initial_status or \
           current_status_text == tr_info_reset_message or \
           current_status_text == en_info_reset_message:
            self.status_text_edit.setText(self.tr("initial_status"))
        elif self.tr("current_disk_info") in current_status_text or \
             self.translations.get("en", {}).get("current_disk_info") in current_status_text:
            selected_text = self.flash_drive_combo.currentText()
            if self.tr("select_drive_placeholder") not in selected_text and selected_text:
                self.status_text_edit.setText(f"{self.tr('current_disk_info')}\n{selected_text}")
            else:
                self.status_text_edit.setText(self.tr("initial_status"))


        if self.flash_drive_combo.count() == 0:
             self.flash_drive_combo.setPlaceholderText(self.tr("select_drive_placeholder"))

        self.start_test_button.setText(self.tr("start_test_button"))
        self.about_button.setText(self.tr("about_button"))


    def _toggle_language(self):
        """Dili Türkçe ve İngilizce arasında değiştirir."""
        self.current_language_index = 1 - self.current_language_index
        self.update_ui_language()
        self._on_disk_selected()
        if not self.is_processing:
             self.status_text_edit.setText(self.tr("initial_status"))

    def _show_about_dialog(self):
        """Hakkında penceresini gösterir."""
        QMessageBox.about(self, self.tr("about_title"), self.tr("about_text"))

    def _load_disks(self):
        """Sistemdeki çıkarılabilir diskleri listeler (Linux için)."""
        self.flash_drive_combo.clear()
        try:
            result = subprocess.run(["lsblk", "--json", "-b"],
                                    capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            disks = []
            for block_device in data.get("blockdevices", []):
                if block_device.get("type") == "disk" and block_device.get("rm") is True:
                    name = "/dev/" + block_device.get("name")
                    size_bytes = int(block_device.get("size", 0))
                    size_human_readable = self._bytes_to_human_readable(size_bytes)

                    mountpoint = block_device.get("mountpoint", None)

                    if mountpoint is None or (mountpoint != "/" and not mountpoint.startswith("/boot")):
                        if not name.startswith("/dev/loop") and \
                           not name.startswith("/dev/ram") and \
                           not name.startswith("/dev/md"):
                            disks.append((name, size_human_readable))

            if not disks:
                self.flash_drive_combo.addItem(self.tr("select_drive_placeholder"))
            else:
                for disk_path, disk_size_hr in disks:
                    self.flash_drive_combo.addItem(f"{disk_path} ({disk_size_hr})")

                if self.flash_drive_combo.count() > 0:
                    self.flash_drive_combo.setCurrentIndex(0)
            print("DEBUG (TERMINAL): Diskler yüklendi.") # YENİ DEBUG

        except FileNotFoundError:
            self.status_text_edit.append(self.tr("Hata: lsblk komutu bulunamadı. Lütfen yüklü olduğundan emin olun."))
            print("DEBUG (TERMINAL): lsblk FileNotFoundError.") # YENİ DEBUG
        except subprocess.CalledProcessError as e:
            self.status_text_edit.append(f"{self.tr('disk_loading_error')} {e.stderr}")
            print(f"DEBUG (TERMINAL): lsblk CalledProcessError: {e.stderr}") # YENİ DEBUG
        except json.JSONDecodeError:
            self.status_text_edit.append(self.tr("Hata: lsblk çıktısı JSON olarak ayrıştırılamadı."))
            print("DEBUG (TERMINAL): lsblk JSONDecodeError.") # YENİ DEBUG
        except Exception as e:
            self.status_text_edit.append(f"{self.tr('disk_loading_error')} {e}")
            print(f"DEBUG (TERMINAL): Unexpected error in _load_disks: {e}") # YENİ DEBUG

        if self.flash_drive_combo.count() == 0:
            self.flash_drive_combo.setPlaceholderText(self.tr("select_drive_placeholder"))

    def _bytes_to_human_readable(self, num_bytes):
        """Bayt cinsinden boyutu okunabilir KB, MB, GB, TB formatına çevirir."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if num_bytes < 1024.0:
                return f"{num_bytes:.2f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.2f} PB"


    def _on_disk_selected(self):
        """Disk combobox'tan bir disk seçildiğinde çalışır."""
        self._reset_info_labels() # Bu metod tüm alanları sıfırlar, sonra yeniden dolduracağız.
        selected_text = self.flash_drive_combo.currentText()
        print(f"DEBUG (TERMINAL): _on_disk_selected çalıştı. Seçilen metin: '{selected_text}'") # YENİ DEBUG

        if not selected_text or self.tr("select_drive_placeholder") in selected_text:
            self.status_text_edit.setText(self.tr("initial_status"))
            self._set_initial_icon()
            print("DEBUG (TERMINAL): Disk seçimi yok veya yer tutucu.") # YENİ DEBUG
            return

        try:
            disk_size_str = selected_text.split("(")[-1].replace(")", "").strip()
            self.promised_capacity_label.setText(f"{self.tr('promised_capacity_label')} {disk_size_str}")
        except IndexError:
            self.promised_capacity_label.setText(f"{self.tr('promised_capacity_label')} {self.tr('not_detected')}")
            print("DEBUG (TERMINAL): Vaadedilen kapasite ayrıştırılamadı.") # YENİ DEBUG

        disk_path = selected_text.split(" ")[0]
        self.status_text_edit.append(f"DEBUG: Seçilen disk yolu: {disk_path}")
        print(f"DEBUG (TERMINAL): Seçilen disk yolu: {disk_path}") # YENİ DEBUG

        brand_model_info = self._get_disk_vendor_product(disk_path)
        self.status_text_edit.append(f"DEBUG: _get_disk_vendor_product'tan alınan: '{brand_model_info}'")
        print(f"DEBUG (TERMINAL): _get_disk_vendor_product'tan alınan: '{brand_model_info}'") # YENİ DEBUG

        if brand_model_info:
            self.brand_model_label.setText(f"{self.tr('brand_model_label')} {brand_model_info}")
            print(f"DEBUG (TERMINAL): Marka/Model etiketi güncellendi: {brand_model_info}") # YENİ DEBUG
        else:
            self.brand_model_label.setText(f"{self.tr('brand_model_label')} {self.tr('not_detected')}")
            print("DEBUG (TERMINAL): Marka/Model tespit edilemedi.") # YENİ DEBUG

        self.status_text_edit.append(f"{self.tr('current_disk_info')}\n{selected_text}")
        self._set_initial_icon()

    def _get_disk_vendor_product(self, disk_path):
        """Diskin marka/model bilgilerini udevadm kullanarak almaya çalışır."""
        self.status_text_edit.append(f"DEBUG: _get_disk_vendor_product çalıştırılıyor: {disk_path}")
        print(f"DEBUG (TERMINAL): _get_disk_vendor_product çalıştırılıyor: {disk_path}") # YENİ DEBUG
        try:
            result = subprocess.run(["udevadm", "info", "-q", "property", "-n", disk_path],
                                    capture_output=True, text=True, check=True)

            self.status_text_edit.append(f"DEBUG: udevadm ham çıktı:\n{result.stdout}")
            print(f"DEBUG (TERMINAL): udevadm ham çıktı:\n{result.stdout}") # YENİ DEBUG

            vendor = None
            model = None

            for line in result.stdout.splitlines():
                if line.startswith("ID_VENDOR_FROM_DATABASE="):
                    vendor = line.split("=")[1].strip()
                elif line.startswith("ID_MODEL_FROM_DATABASE="):
                    model = line.split("=")[1].strip()
                elif line.startswith("ID_VENDOR=") and vendor is None:
                    vendor = line.split("=")[1].strip()
                elif line.startswith("ID_MODEL=") and model is None:
                    model = line.split("=")[1].strip()
                # Ek kontrol: Eğer önceki satırlardan alınmadıysa ve ID_VENDOR_ENC varsa
                elif line.startswith("ID_VENDOR_ENC=") and vendor is None:
                    vendor = line.split("=")[1].strip()
                # Ek kontrol: Eğer önceki satırlardan alınmadıysa ve ID_MODEL_ENC varsa
                elif line.startswith("ID_MODEL_ENC=") and model is None:
                    model = line.split("=")[1].strip()

            info_parts = []
            if vendor:
                info_parts.append(vendor)
            if model:
                info_parts.append(model)

            self.status_text_edit.append(f"DEBUG: Ayrıştırılan Vendor: {vendor}, Model: {model}")
            print(f"DEBUG (TERMINAL): Ayrıştırılan Vendor: {vendor}, Model: {model}") # YENİ DEBUG

            if info_parts:
                final_info = " ".join(info_parts)
                self.status_text_edit.append(f"DEBUG: Döndürülen marka/model: {final_info}")
                print(f"DEBUG (TERMINAL): Döndürülen marka/model: {final_info}") # YENİ DEBUG
                return final_info

            self.status_text_edit.append("DEBUG: Marka/Model bulunamadı, None döndürüldü.")
            print("DEBUG (TERMINAL): Marka/Model bulunamadı, None döndürüldü.") # YENİ DEBUG
            return None

        except FileNotFoundError:
            self.status_text_edit.append(f"<font color='red'>Hata: udevadm bulunamadı veya PATH'te değil.</font>")
            print(f"DEBUG (TERMINAL): Hata: udevadm bulunamadı veya PATH'te değil.") # YENİ DEBUG
            return None
        except subprocess.CalledProcessError as e:
            self.status_text_edit.append(f"<font color='red'>Hata: udevadm komutu başarısız oldu: {e.stderr}</font>")
            print(f"DEBUG (TERMINAL): Hata: udevadm komutu başarısız oldu: {e.stderr}") # YENİ DEBUG
            return None
        except Exception as e:
            self.status_text_edit.append(f"<font color='red'>Hata: udevadm işlenirken beklenmeyen hata: {e}</font>")
            print(f"DEBUG (TERMINAL): Hata: udevadm işlenirken beklenmeyen hata: {e}") # YENİ DEBUG
            return None

    def _get_selected_disk_path(self):
        """Seçili diskin /dev/sdX yolunu döndürür."""
        selected_text = self.flash_drive_combo.currentText()
        if not selected_text or self.tr("select_drive_placeholder") in selected_text:
            QMessageBox.warning(self, self.tr("select_drive_warning_title"), self.tr("select_drive_warning_text"))
            return None

        disk_path = selected_text.split(" ")[0]

        if not disk_path.startswith("/dev/"):
            QMessageBox.critical(self, self.tr("invalid_disk_selection"), self.tr("invalid_disk_selection"))
            return None

        return disk_path

    def _set_processing_state(self, processing):
        """GUI butonlarını işlem durumuna göre etkinleştirir/devre dışı bırakır."""
        self.is_processing = processing
        self.start_test_button.setEnabled(not processing)
        self.language_button.setEnabled(not processing)
        self.about_button.setEnabled(not processing)
        self.flash_drive_combo.setEnabled(not processing)

        if processing:
            scanning_icon_path = self.icon_paths.get("flashicon_scanning.gif")
            self._set_icon_to_label(scanning_icon_path)
        else:
            pass


    def _reset_info_labels(self):
        """Tüm bilgi etiketlerini başlangıç değerlerine sıfırlar."""
        # Bu metod _on_disk_selected tarafından çağrılır ve tüm alanları sıfırlar.
        # Marka/Model ve Vaadedilen Kapasite hemen sonra yeniden doldurulur.
        # Gerçek Kapasite ise test sonucunda dolacak.
        self.brand_model_label.setText(f"{self.tr('brand_model_label')} {self.tr('not_detected')}")
        self.promised_capacity_label.setText(f"{self.tr('promised_capacity_label')} {self.tr('not_detected')}")
        self.real_capacity_label.setText(f"{self.tr('real_capacity_label')} {self.tr('not_tested')}")


    def _start_test(self):
        """Tek test (f3probe) başlatma mantığı."""
        if self.is_processing:
            return

        disk_path = self._get_selected_disk_path()
        if not disk_path:
            return

        self._set_processing_state(True)
        
        # Sadece gerçek kapasite bilgisini test başlangıcında sıfırla
        self.real_capacity_label.setText(f"{self.tr('real_capacity_label')} {self.tr('not_tested')}")

        # Durum penceresini temizle ve mevcut disk bilgisini tekrar ekle
        self.status_text_edit.clear()
        selected_disk_text = self.flash_drive_combo.currentText()
        if selected_disk_text and self.tr("select_drive_placeholder") not in selected_disk_text:
            self.status_text_edit.append(f"{self.tr('current_disk_info')}\n{selected_disk_text}\n")
        self.status_text_edit.append(self.tr("processing_message"))
        print("DEBUG (TERMINAL): Test başlatma butonu tıklandı.") # YENİ DEBUG


        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()

        self.worker = F3Worker(disk_path, self.translations, self.current_language_index)
        self.worker.finished.connect(self._test_finished)
        self.worker.progress.connect(self._update_status_text)
        self.worker.error.connect(self._test_error)
        self.worker.f3probe_result.connect(self._update_f3probe_results)
        self.worker.start()

    def _update_status_text(self, text):
        """Worker'dan gelen ilerleme mesajlarını durum kutusuna ekler."""
        self.status_text_edit.append(text.strip())
        QApplication.processEvents()

    def _test_finished(self, message):
        """Test başarıyla tamamlandığında."""
        self.status_text_edit.append(message)
        print(f"DEBUG (TERMINAL): Test finished: {message}") # YENİ DEBUG

    def _test_error(self, message):
        """Test sırasında bir hata oluştuğunda."""
        if self.tr("pkexec_not_found") in message:
            self.status_text_edit.append(f"<font color='red'>{self.tr('pkexec_not_found')}</font>")
        elif self.tr("authentication_error").split('\n')[0] in message:
            original_detail = message.split("Detay: ", 1)[-1] if "Detay: " in message else ""
            self.status_text_edit.append(f"<font color='red'>{self.tr('authentication_error').format(detail=original_detail)}</font>")
        elif self.tr("f3_not_found_error") in message:
             self.status_text_edit.append(f"<font color='red'>{self.tr('f3_not_found_error')}</font>")
        elif self.tr("unexpected_error") in message:
             self.status_text_edit.append(f"<font color='red'>{self.tr('unexpected_error')}</font>")
        elif self.tr("f3probe_capacity_parse_error") in message:
             self.status_text_edit.append(f"<font color='red'>{self.tr('f3probe_capacity_parse_error')}</font>")
        else:
            self.status_text_edit.append(f"<font color='red'>{message}</font>")
        self._set_processing_state(False)
        fail_icon_path = self.icon_paths.get("flashicon_testFAIL.png")
        self._set_icon_to_label(fail_icon_path)
        print(f"DEBUG (TERMINAL): Test error: {message}") # YENİ DEBUG

    def _update_f3probe_results(self, real_capacity, promised_capacity, brand_model, status_message):
        """f3probe test sonuçlarını GUI'ye yansıtır."""
        self.real_capacity_label.setText(f"{self.tr('real_capacity_label')} {real_capacity}")
        print(f"DEBUG (TERMINAL): Real capacity updated: {real_capacity}") # YENİ DEBUG

        if promised_capacity != self.tr("not_detected"):
            self.promised_capacity_label.setText(f"{self.tr('promised_capacity_label')} {promised_capacity}")
            print(f"DEBUG (TERMINAL): Promised capacity updated: {promised_capacity}") # YENİ DEBUG

        # DÜZELTME: Marka/Model bilgisi udevadm'den gelir, f3probe'dan değil.
        # Bu kısım _update_f3probe_results metodundan kaldırıldı.
        # if brand_model != self.tr("not_detected") and brand_model != "":
        #     self.brand_model_label.setText(f"{self.tr('brand_model_label')} {brand_model}")
        #     print(f"DEBUG (TERMINAL): Brand/Model label updated: {brand_model}")
        # else:
        #     self.brand_model_label.setText(f"{self.tr('brand_model_label')} {self.tr('not_detected')}")
        #     print("DEBUG (TERMINAL): Brand/Model label set to not detected.")


        if self.tr("fake_warning") in status_message or self.tr("capacity_mismatch_warning") in status_message:
            self.status_text_edit.append(f"<font color='red'>{status_message}</font>")
            fail_icon_path = self.icon_paths.get("flashicon_testFAIL.png")
            self._set_icon_to_label(fail_icon_path)
        else:  # Test başarılı veya gerçek çıktı
            self.status_text_edit.append(f"<font color='green'>{status_message}</font>")
            ok_icon_path = self.icon_paths.get("flashicon_testOK.png")
            self._set_icon_to_label(ok_icon_path)

        self._set_processing_state(False)
        print("DEBUG (TERMINAL): Processing state set to False.") # YENİ DEBUG


if __name__ == '__main__':
    app = QApplication(sys.argv)

    app_font = QFont("Arial", 10)
    app.setFont(app_font)

    app.setApplicationName("Fake USB Tester")

    window = FakeUSBTesterApp()
    window.show()
    sys.exit(app.exec_())
