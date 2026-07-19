with open('d:/project/dien-luc/templates/stations/station_list.html', 'r', encoding='utf-8') as f:
    content = f.read()

old_form = """<form action="{% url 'global_bulk_create' %}" method="POST" class="space-y-4">
                    {% csrf_token %}
                    <div class="bg-blue-50 border border-blue-100 text-blue-800 p-4 rounded-lg text-sm space-y-2">
                        <p class="font-bold"><i class="fas fa-info-circle mr-1"></i> Hướng dẫn nhập liệu một bước:</p>
                        <p>Sao chép dữ liệu từ Excel và dán vào ô bên dưới. Yêu cầu định dạng bảng gồm ít nhất 5 cột (cột 6,7 là tùy chọn). Các cột cách nhau bằng phím Tab (mặc định khi copy từ Excel).</p>
                        <div class="bg-white p-2 rounded border border-blue-200 font-mono text-xs overflow-x-auto">
                            Mã Trạm | Tên Trạm | Mã Ngăn lộ | Tên Ngăn lộ | Mã Rơ-le | Tên Rơ-le (Tùy chọn) | Hãng SX (Tùy chọn)
                        </div>
                        <p class="text-xs text-blue-600 italic">Hệ thống sẽ tự động đối chiếu: Nếu Trạm hoặc Ngăn lộ chưa tồn tại, hệ thống sẽ tự động tạo mới!</p>
                    </div>
                    <textarea name="raw_text" rows="12" required class="w-full p-3 border border-slate-300 rounded focus:border-amber-500 outline-none font-mono text-sm whitespace-pre text-nowrap overflow-auto bg-slate-50" placeholder="Mã Trạm	Tên Trạm	Mã Ngăn lộ	Tên Ngăn lộ	Mã Rơ-le..."></textarea>
                    
                    <div class="flex justify-end gap-2 pt-2">
                        <button type="button" @click="showGlobalBulkModal = false" class="px-4 py-2 text-sm text-slate-600 bg-slate-100 hover:bg-slate-200 rounded font-medium">Hủy</button>
                        <button type="submit" class="px-6 py-2 text-sm text-white bg-amber-600 hover:bg-amber-700 rounded shadow-sm font-bold"><i class="fas fa-upload mr-1"></i> Bắt đầu Nạp Dữ Liệu</button>
                    </div>
                </form>"""

new_form = """<form action="{% url 'global_bulk_create' %}" method="POST" enctype="multipart/form-data" class="space-y-4">
                    {% csrf_token %}
                    <div class="bg-blue-50 border border-blue-100 text-blue-800 p-4 rounded-lg text-sm space-y-2 mb-6">
                        <p class="font-bold"><i class="fas fa-info-circle mr-1"></i> Hướng dẫn tải file Excel:</p>
                        <p>Hệ thống tự động đọc file Excel (.xlsx hoặc .xls) của bạn. <b>Lưu ý: Bỏ qua dòng đầu tiên (dòng tiêu đề).</b></p>
                        <p>Yêu cầu thứ tự 7 cột như sau (Cột F và G có thể để trống):</p>
                        <div class="bg-white p-2 rounded border border-blue-200 font-mono text-xs overflow-x-auto text-center">
                            Cột A (Mã Trạm) | Cột B (Tên Trạm) | Cột C (Mã Ngăn lộ) | Cột D (Tên Ngăn lộ) | Cột E (Mã Rơ-le) | Cột F (Tên Rơ-le) | Cột G (Hãng SX)
                        </div>
                        <p class="text-xs text-blue-600 italic">Hệ thống sẽ tự động đối chiếu: Nếu Trạm hoặc Ngăn lộ chưa tồn tại, hệ thống sẽ tự động tạo mới!</p>
                    </div>
                    
                    <div class="border-2 border-dashed border-amber-300 bg-amber-50/50 p-10 text-center rounded-xl hover:bg-amber-50 transition-colors cursor-pointer relative">
                        <i class="fas fa-file-excel text-5xl text-amber-400 mb-4"></i>
                        <h4 class="text-lg font-bold text-slate-700 mb-1">Kéo thả hoặc Chọn file Excel</h4>
                        <p class="text-sm text-slate-500 mb-4">Chấp nhận định dạng .xlsx, .xls</p>
                        <input type="file" name="excel_file" accept=".xlsx, .xls" required class="absolute inset-0 w-full h-full opacity-0 cursor-pointer">
                        <span class="inline-block px-4 py-2 bg-white border border-slate-300 rounded text-sm text-slate-600 font-medium">Chọn File</span>
                    </div>
                    
                    <div class="flex justify-end gap-2 pt-4">
                        <button type="button" @click="showGlobalBulkModal = false" class="px-4 py-2 text-sm text-slate-600 bg-slate-100 hover:bg-slate-200 rounded font-medium transition-colors">Hủy</button>
                        <button type="submit" class="px-6 py-2 text-sm text-white bg-amber-600 hover:bg-amber-700 rounded shadow-sm font-bold transition-colors"><i class="fas fa-cogs mr-1"></i> Tự động Xử lý File</button>
                    </div>
                </form>"""

content = content.replace(old_form, new_form)

with open('d:/project/dien-luc/templates/stations/station_list.html', 'w', encoding='utf-8') as f:
    f.write(content)
