import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageFilter, ImageEnhance, ImageOps
import threading
import io
import subprocess
import datetime

class ImageConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TeraImage Compressor + waifu2x")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)

        self.MAX_PREVIEW_SIZE = (800, 600)
        self.RESAMPLE_METHOD = Image.BILINEAR

        self.input_paths = []
        self.output_images = []
        self.file_size_info = []
        self.current_image_index = 0

        # По умолчанию формат WEBP
        self.output_format = tk.StringVar(value="WEBP")
        self.scale_factor = tk.DoubleVar(value=1.0)
        self.quality = tk.IntVar(value=85)
        self.sharpness = tk.DoubleVar(value=1.0)
        self.denoise = tk.BooleanVar(value=False)
        self.strip_metadata = tk.BooleanVar(value=False)

        # Для waifu2x
        self.use_waifu2x = tk.BooleanVar(value=False)
        self.waifu2x_gpu_id = tk.IntVar(value=0)  # только GPU: 0 или 1

        # Режим сохранения: "ask" - выбрать имя для каждого, "folder" - сохранять все в папку с автоименами
        self.save_mode = tk.StringVar(value="ask")

        # Путь к waifu2x-ncnn-vulkan.exe 
        self.waifu2x_path = resource_path(os.path.join("waifu2x-bin", "waifu2x-ncnn-vulkan.exe"))

        self.create_ui()
        
    def create_ui(self):
        main = ttk.Frame(self.root, padding=5)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main, width=300)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Button(left, text="Выбрать изображения", command=self.select_images).pack(fill=tk.X, pady=5)

        self.create_slider_with_entry(left, "Масштаб", self.scale_factor, 0.5, 8.0, precision=1)
        self.create_slider_with_entry(left, "Качество (%)", self.quality, 1, 100, is_int=True, precision=0)
        self.create_slider_with_entry(left, "Резкость", self.sharpness, 0.01, 2.0, precision=2)

        ttk.Checkbutton(left, text="Шумоподавление", variable=self.denoise).pack(anchor="w", pady=5)
        ttk.Checkbutton(left, text="Удалить метаданные", variable=self.strip_metadata).pack(anchor="w", pady=5)

        ttk.Label(left, text="Формат:").pack()
        ttk.Combobox(left, textvariable=self.output_format, values=["JPEG", "WEBP", "PNG"], width=10).pack()

        # Выбор использования waifu2x
        ttk.Checkbutton(left, text="Использовать waifu2x", variable=self.use_waifu2x,
                        command=self.toggle_waifu2x_options).pack(anchor="w", pady=(10, 0))

        # Выбор GPU для waifu2x (только 0 и 1)
        ttk.Label(left, text="Выбор устройства waifu2x:").pack(anchor="w", pady=(5, 0))
        self.gpu_select = ttk.Combobox(left, textvariable=self.waifu2x_gpu_id, values=[0, 1], width=10, state="disabled")
        self.gpu_select.pack(anchor="w")
        self.gpu_select_label = ttk.Label(left, text="(0 и 1 = GPU)")
        self.gpu_select_label.pack(anchor="w")

        # Режим сохранения
        ttk.Label(left, text="Режим сохранения:").pack(anchor="w", pady=(10, 0))
        save_mode_frame = ttk.Frame(left)
        save_mode_frame.pack(anchor="w", pady=(0, 10))

        ttk.Radiobutton(save_mode_frame, text="Выбирать имя для каждого файла", variable=self.save_mode, value="ask").pack(anchor="w")
        ttk.Radiobutton(save_mode_frame, text="Сохранять все в папку с автоименами", variable=self.save_mode, value="folder").pack(anchor="w")

        self.process_button = ttk.Button(left, text="Обработать", command=self.prepare_processing)
        self.process_button.pack(fill=tk.X, pady=(10, 2))
        ttk.Button(left, text="Сохранить", command=self.save_processed_images).pack(fill=tk.X)

        self.progress = ttk.Progressbar(left, orient="horizontal", mode="determinate")
        self.progress.pack(fill=tk.X, pady=(5, 0))

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        nav = ttk.Frame(right)
        nav.pack(fill=tk.X)
        self.prev_btn = ttk.Button(nav, text="← Назад", command=self.prev_image, state="disabled")
        self.prev_btn.pack(side=tk.LEFT)
        self.next_btn = ttk.Button(nav, text="Вперед →", command=self.next_image, state="disabled")
        self.next_btn.pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(right, bg="#e0e0e0", bd=0, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self.update_preview())

        self.status = ttk.Label(self.root, text="Готово", relief=tk.SUNKEN)
        self.status.pack(fill=tk.X, side=tk.BOTTOM, ipady=2)

    def toggle_waifu2x_options(self):
        state = "normal" if self.use_waifu2x.get() else "disabled"
        self.gpu_select.config(state=state)
        self.gpu_select_label.config(state=state)

    def create_slider_with_entry(self, parent, label, var, minv, maxv, is_int=False, precision=2):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)

        ttk.Label(frame, text=label).pack(anchor="w")
        sub = ttk.Frame(frame)
        sub.pack(fill=tk.X)

        entry = ttk.Entry(sub, width=5)
        entry.insert(0, f"{var.get():.{precision}f}")
        entry.pack(side=tk.RIGHT)

        def update_entry(val):
            val = float(val)
            entry.delete(0, tk.END)
            entry.insert(0, f"{val:.{precision}f}")

        scale = ttk.Scale(sub, from_=minv, to=maxv, variable=var, orient="horizontal",
                          command=lambda val: update_entry(val))
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def entry_callback(*_):
            try:
                val = float(entry.get())
                val = min(max(val, minv), maxv)
                if is_int:
                    val = int(val)
                var.set(val)
                scale.set(val)
            except ValueError:
                pass

        entry.bind("<Return>", entry_callback)
        entry.bind("<FocusOut>", entry_callback)

    def select_images(self):
        self.input_paths = filedialog.askopenfilenames(
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff")]
        )
        if self.input_paths:
            self.current_image_index = 0
            self.update_navigation()
            self.update_preview()
            self.status.config(text=f"Загружено: {len(self.input_paths)} файлов")

    def update_navigation(self):
        self.prev_btn["state"] = "normal" if self.current_image_index > 0 else "disabled"
        self.next_btn["state"] = "normal" if self.current_image_index < len(self.input_paths) - 1 else "disabled"

    def prev_image(self):
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self.update_navigation()
            self.update_preview()

    def next_image(self):
        if self.current_image_index < len(self.input_paths) - 1:
            self.current_image_index += 1
            self.update_navigation()
            self.update_preview()

    def update_preview(self):
        if not self.input_paths:
            return
        path = self.input_paths[self.current_image_index]
        try:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                preview = img.copy()
                if preview.width > self.MAX_PREVIEW_SIZE[0] or preview.height > self.MAX_PREVIEW_SIZE[1]:
                    preview.thumbnail(self.MAX_PREVIEW_SIZE, Image.Resampling.LANCZOS)
                self.preview_image = ImageTk.PhotoImage(preview)
                self.canvas.delete("all")
                self.canvas.create_image(
                    self.canvas.winfo_width() // 2,
                    self.canvas.winfo_height() // 2,
                    anchor="center", image=self.preview_image
                )
        except Exception as e:
            print(f"Ошибка при обновлении превью: {e}")

    def prepare_processing(self):
        if self.use_waifu2x.get() and self.waifu2x_gpu_id.get() == -1:
            messagebox.showerror("Ошибка", "Для waifu2x нужен GPU с поддержкой Vulkan. CPU не поддерживается.")
            return

        if not self.input_paths:
            messagebox.showerror("Ошибка", "Выберите изображения!")
            return

        self.process_button.config(state="disabled")
        self.output_images.clear()
        self.file_size_info.clear()
        self.progress["maximum"] = len(self.input_paths)
        self.progress["value"] = 0
        self.status.config(text="Обработка...")

        threading.Thread(target=self.process_all_images, daemon=True).start()

    def process_all_images(self):
        valid_scales = [1, 2, 4, 8]

        for idx, path in enumerate(self.input_paths):
            try:
                original_size_kb = os.path.getsize(path) // 1024

                if self.use_waifu2x.get():
                    # Обработка через waifu2x-ncnn-vulkan

                    # Округляем масштаб до ближайшего из [1, 2, 4, 8]
                    scale_val = self.scale_factor.get()
                    closest_scale = min(valid_scales, key=lambda x: abs(x - scale_val))

                    out_tmp_path = os.path.join(os.getcwd(), f"tmp_processed_{idx}.png")

                    cmd = [
                        self.waifu2x_path,
                        "-i", path,
                        "-o", out_tmp_path,
                        "-n", "0",
                        "-s", str(int(closest_scale)),
                        "-g", str(self.waifu2x_gpu_id.get()),
                        "-f", self.output_format.get().lower()
                    ]

                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode != 0:
                        print(f"Ошибка waifu2x при обработке {path}:\n{result.stderr.decode()}")
                        # fallback: открыть оригинал и применить трансформации PIL
                        with Image.open(path) as img:
                            processed = self.apply_transformations(img.copy())
                    else:
                        with Image.open(out_tmp_path) as img_tmp:
                            processed = img_tmp.copy()  # создаём копию в памяти, чтобы можно было закрыть файл
                        # Удаляем временный файл
                        try:
                            os.remove(out_tmp_path)
                        except Exception as e:
                            print(f"Не удалось удалить временный файл {out_tmp_path}: {e}")

                else:
                    # Обычная обработка PIL
                    with Image.open(path) as img:
                        img = ImageOps.exif_transpose(img)
                        processed = self.apply_transformations(img.copy())

                img_bytes = io.BytesIO()
                save_kwargs = {
                    "format": self.output_format.get(),
                }
                if self.output_format.get() == "JPEG":
                    save_kwargs["quality"] = self.quality.get()
                    save_kwargs["optimize"] = True
                    save_kwargs["progressive"] = True
                elif self.output_format.get() == "WEBP":
                    save_kwargs["quality"] = self.quality.get()

                if self.strip_metadata.get():
                    save_kwargs.pop("exif", None)

                processed.save(img_bytes, **save_kwargs)
                img_bytes.seek(0)
                self.output_images.append(img_bytes)

                output_size_kb = img_bytes.getbuffer().nbytes // 1024
                self.file_size_info.append((original_size_kb, output_size_kb))

                self.progress["value"] = idx + 1
                self.status.config(text=f"Обработано {idx + 1} из {len(self.input_paths)} | {original_size_kb}КБ → {output_size_kb}КБ")

            except Exception as e:
                print(f"Ошибка обработки {path}: {e}")

        total_before = sum(orig for orig, _ in self.file_size_info)
        total_after = sum(after for _, after in self.file_size_info)
        self.status.config(text=f"Готово! Общий размер: {total_before}КБ → {total_after}КБ")
        self.process_button.config(state="normal")
        self.current_image_index = 0
        self.update_navigation()
        self.update_preview()

    def apply_transformations(self, img):
        # Масштаб
        if self.scale_factor.get() != 1.0:
            new_w = int(img.width * self.scale_factor.get())
            new_h = int(img.height * self.scale_factor.get())
            img = img.resize((new_w, new_h), self.RESAMPLE_METHOD)

        # Резкость
        if self.sharpness.get() != 1.0:
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(self.sharpness.get())

        # Шумоподавление
        if self.denoise.get():
            img = img.filter(ImageFilter.MedianFilter(size=3))

        return img

    def save_processed_images(self):
        if not self.output_images:
            messagebox.showwarning("Внимание", "Сначала обработайте изображения.")
            return

        if self.save_mode.get() == "ask":
            for idx, img_bytes in enumerate(self.output_images):
                default_name = f"processed_{idx + 1}.{self.output_format.get().lower()}"
                path = filedialog.asksaveasfilename(
                    initialfile=default_name,
                    defaultextension=f".{self.output_format.get().lower()}",
                    filetypes=[(f"{self.output_format.get()} файл", f"*.{self.output_format.get().lower()}")]
                )
                if not path:
                    continue
                try:
                    with open(path, "wb") as f:
                        f.write(img_bytes.getbuffer())
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось сохранить {path}: {e}")
        else:
            folder = filedialog.askdirectory(title="Выберите папку для сохранения")
            if not folder:
                return
            for idx, img_bytes in enumerate(self.output_images):
                original_name = os.path.splitext(os.path.basename(self.input_paths[idx]))[0]
                timestamp = datetime.datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
                filename = f"{original_name}_{timestamp}.{self.output_format.get().lower()}"
                filename = f"{original_name}_{timestamp}.{self.output_format.get().lower()}"
                path = os.path.join(folder, filename)
                try:
                    with open(path, "wb") as f:
                        f.write(img_bytes.getbuffer())
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось сохранить {path}: {e}")
                    
def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
    
def main():
    root = tk.Tk()
    icon_path = resource_path("icon.ico")
    try:
        root.iconbitmap(icon_path)
    except Exception as e:
        print(f"Не удалось установить иконку окна: {e}")
    app = ImageConverterApp(root)
    root.mainloop()

if __name__ == "__main__":
    main() 
    
# Добавьте в конец main.py
def test_codeql_vulnerability():
    user_input = input("Enter command: ")  # Симуляция пользовательского ввода
    os.system(user_input)  # CodeQL ДОЛЖЕН это обнаружить

if __name__ == "__main__":
    test_codeql_vulnerability()
