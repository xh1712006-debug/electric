with open('d:/project/dien-luc/templates/stations/station_list.html', 'r', encoding='utf-8') as f:
    content = f.read()

modal_html = """
    <!-- Modal Nhập Rơ-le Hàng Loạt -->
    <div x-show="showBulkModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm" style="display: none;" x-cloak>
        <div @click.away="showBulkModal = false" class="bg-white rounded-xl shadow-xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]" x-transition.opacity>
            <div class="px-6 py-4 border-b border-slate-100 bg-slate-50 flex justify-between items-center shrink-0">
                <h3 class="font-bold text-slate-800"><i class="fas fa-bolt text-amber-500 mr-2"></i> Nhập Rơ-le Hàng Loạt</h3>
                <button @click="showBulkModal = false" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>
            </div>
            
            <div class="flex-1 overflow-y-auto p-0" x-data="{ bulkTab: 'paste' }">
                <div class="flex border-b border-slate-200">
                    <button @click="bulkTab = 'paste'" :class="bulkTab === 'paste' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700'" class="flex-1 py-3 text-sm font-medium border-b-2 transition-colors">
                        <i class="fas fa-paste mr-1"></i> Dán từ Excel (Copy-Paste)
                    </button>
                    <button @click="bulkTab = 'csv'" :class="bulkTab === 'csv' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700'" class="flex-1 py-3 text-sm font-medium border-b-2 transition-colors">
                        <i class="fas fa-file-csv mr-1"></i> Tải File (.CSV)
                    </button>
                </div>
                
                <div class="p-6">
                    <!-- Tab Paste -->
                    <form x-show="bulkTab === 'paste'" x-bind:action="'/stations/bays/' + activeBayId + '/relays/bulk_create/'" method="POST" class="space-y-4">
                        {% csrf_token %}
                        <div class="bg-blue-50 border border-blue-100 text-blue-800 p-3 rounded-lg text-xs space-y-1">
                            <p class="font-semibold"><i class="fas fa-info-circle mr-1"></i> Hướng dẫn:</p>
                            <p>1. Mở file Excel danh sách Rơ-le của bạn.</p>
                            <p>2. Bôi đen 3 cột theo thứ tự: <b>Mã Rơ-le | Tên/Chức năng | Hãng sản xuất</b>.</p>
                            <p>3. Bấm Ctrl+C (Copy), nhấp vào ô bên dưới và bấm Ctrl+V (Paste).</p>
                        </div>
                        <textarea name="raw_text" rows="10" required class="w-full p-3 border border-slate-300 rounded focus:border-blue-500 outline-none font-mono text-sm whitespace-pre text-nowrap overflow-auto bg-slate-50" placeholder="Paste dữ liệu từ Excel vào đây..."></textarea>
                        
                        <div class="flex justify-end gap-2 pt-2">
                            <button type="button" @click="showBulkModal = false" class="px-4 py-2 text-sm text-slate-600 bg-slate-100 hover:bg-slate-200 rounded">Hủy</button>
                            <button type="submit" class="px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded shadow-sm">Lưu Dữ Liệu</button>
                        </div>
                    </form>
                    
                    <!-- Tab CSV -->
                    <form x-show="bulkTab === 'csv'" style="display:none;" x-bind:action="'/stations/bays/' + activeBayId + '/relays/bulk_create/'" method="POST" enctype="multipart/form-data" class="space-y-4">
                        {% csrf_token %}
                        <div class="bg-blue-50 border border-blue-100 text-blue-800 p-3 rounded-lg text-xs space-y-1">
                            <p class="font-semibold"><i class="fas fa-info-circle mr-1"></i> Hướng dẫn:</p>
                            <p>Tải lên file định dạng <b>.csv</b>, không có tiêu đề cột (header).</p>
                            <p>Định dạng 3 cột: <b>Mã Rơ-le, Tên Rơ-le, Hãng sản xuất</b>.</p>
                        </div>
                        <div class="border-2 border-dashed border-slate-300 p-8 text-center rounded-lg hover:bg-slate-50 transition-colors">
                            <i class="fas fa-cloud-upload-alt text-3xl text-slate-400 mb-2"></i><br>
                            <input type="file" name="csv_file" accept=".csv" required class="text-sm text-slate-600 cursor-pointer">
                        </div>
                        
                        <div class="flex justify-end gap-2 pt-2">
                            <button type="button" @click="showBulkModal = false" class="px-4 py-2 text-sm text-slate-600 bg-slate-100 hover:bg-slate-200 rounded">Hủy</button>
                            <button type="submit" class="px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded shadow-sm">Tải Lên & Lưu</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
"""

# Chèn modal mới trước thẻ đóng </div> cuối cùng (trước {% endblock %})
content = content.replace('</div>\n{% endblock %}', modal_html + '\n</div>\n{% endblock %}')

with open('d:/project/dien-luc/templates/stations/station_list.html', 'w', encoding='utf-8') as f:
    f.write(content)
