import re

with open('d:/project/dien-luc/templates/stations/station_list.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update root x-data
content = content.replace(
    'x-data="{ showStationModal: false, showBayModal: false, showRelayModal: false, showBulkModal: false, activeStationId: null, activeBayId: null, searchQuery: \'\' }"',
    'x-data="{ showStationModal: false, showBayModal: false, showRelayModal: false, showBulkModal: false, showGlobalBulkModal: false, activeStationId: null, activeBayId: null, searchStation: \'\', searchBay: \'\', searchRelay: \'\' }"'
)

# 2. Add Global Import Button
content = content.replace(
    '<button @click="showStationModal = true" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">\n            <i class="fas fa-plus mr-1"></i> Thêm Trạm mới\n        </button>',
    '''<div class="flex gap-2">
            <button @click="showGlobalBulkModal = true" class="px-4 py-2 bg-amber-500 text-white rounded-lg text-sm font-semibold hover:bg-amber-600 transition-colors shadow-sm border border-amber-600">
                <i class="fas fa-bolt mr-1"></i> Nhập Liệu Toàn Cục
            </button>
            <button @click="showStationModal = true" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">
                <i class="fas fa-plus mr-1"></i> Thêm Trạm mới
            </button>
        </div>'''
)

# 3. Replace old search bar with 3-column search bar
old_search = '''    <div class="mb-6 relative">
        <i class="fas fa-search absolute left-4 top-3 text-slate-400"></i>
        <input type="text" x-model="searchQuery" placeholder="Tìm kiếm nhanh Trạm, Ngăn lộ, Rơ-le..." class="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:border-blue-500 focus:bg-white outline-none transition-colors">
    </div>'''

new_search = '''    <div class="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- Station Search -->
        <div class="relative">
            <i class="fas fa-search absolute left-3 top-3 text-slate-400 text-sm"></i>
            <input type="text" x-model="searchStation" list="dl-stations" placeholder="Chọn hoặc nhập tên Trạm..." class="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:border-blue-500 focus:bg-white outline-none transition-colors text-sm">
            <datalist id="dl-stations">
                {% for s in stations %}<option value="{{ s.station_code }}">{{ s.station_name }}</option>{% endfor %}
            </datalist>
        </div>
        <!-- Bay Search -->
        <div class="relative">
            <i class="fas fa-search absolute left-3 top-3 text-slate-400 text-sm"></i>
            <input type="text" x-model="searchBay" list="dl-bays" placeholder="Chọn hoặc nhập Ngăn lộ..." class="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:border-blue-500 focus:bg-white outline-none transition-colors text-sm">
            <datalist id="dl-bays">
                {% for s in stations %}{% for b in s.bays.all %}<option value="{{ b.bay_code }}">{{ b.bay_name }}</option>{% endfor %}{% endfor %}
            </datalist>
        </div>
        <!-- Relay Search -->
        <div class="relative">
            <i class="fas fa-search absolute left-3 top-3 text-slate-400 text-sm"></i>
            <input type="text" x-model="searchRelay" list="dl-relays" placeholder="Chọn hoặc nhập Rơ-le..." class="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:border-blue-500 focus:bg-white outline-none transition-colors text-sm">
            <datalist id="dl-relays">
                {% for s in stations %}{% for b in s.bays.all %}{% for r in b.relays.all %}<option value="{{ r.relay_code }}">{{ r.relay_name }}</option>{% endfor %}{% endfor %}{% endfor %}
            </datalist>
        </div>
    </div>'''
content = content.replace(old_search, new_search)

# 4. Update Station Box x-show
content = content.replace(
    'x-show="searchQuery === \'\' || $el.innerText.toLowerCase().includes(searchQuery.toLowerCase())"',
    'x-show="(searchStation === \'\' || $el.innerText.toLowerCase().includes(searchStation.toLowerCase())) && (searchBay === \'\' || $el.innerText.toLowerCase().includes(searchBay.toLowerCase())) && (searchRelay === \'\' || $el.innerText.toLowerCase().includes(searchRelay.toLowerCase()))"'
)

# 5. Update Station Body x-show (Auto-expand if Bay or Relay is searched)
content = content.replace(
    'x-show="expandedStation || searchQuery !== \'\'"',
    'x-show="expandedStation || searchBay !== \'\' || searchRelay !== \'\'"'
)

# 6. Add x-show to Bay Box
content = content.replace(
    '<div class="ml-6 border-l-2 border-blue-200 pl-4 relative" x-data="{ expanded: false }">',
    '<div class="ml-6 border-l-2 border-blue-200 pl-4 relative" x-data="{ expanded: false }" x-show="(searchBay === \'\' || $el.innerText.toLowerCase().includes(searchBay.toLowerCase())) && (searchRelay === \'\' || $el.innerText.toLowerCase().includes(searchRelay.toLowerCase()))">'
)

# 7. Update Bay Body x-show (Auto-expand if Relay is searched)
content = content.replace(
    'x-show="expanded || searchQuery !== \'\'"',
    'x-show="expanded || searchRelay !== \'\'"'
)

# 8. Update Relay Row x-show
content = content.replace(
    '<tr class="hover:bg-blue-50/50 transition-colors group" x-show="searchQuery === \'\' || $el.innerText.toLowerCase().includes(searchQuery.toLowerCase())">',
    '<tr class="hover:bg-blue-50/50 transition-colors group" x-show="searchRelay === \'\' || $el.innerText.toLowerCase().includes(searchRelay.toLowerCase())">'
)

# 9. Append Global Bulk Modal
global_modal = """
    <!-- Modal Nhập Liệu Toàn Cục -->
    <div x-show="showGlobalBulkModal" class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm" style="display: none;" x-cloak>
        <div @click.away="showGlobalBulkModal = false" class="bg-white rounded-xl shadow-xl w-full max-w-4xl overflow-hidden flex flex-col max-h-[90vh]" x-transition.opacity>
            <div class="px-6 py-4 border-b border-slate-100 bg-amber-50 flex justify-between items-center shrink-0">
                <h3 class="font-bold text-amber-900"><i class="fas fa-bolt text-amber-500 mr-2"></i> Nhập Liệu Toàn Cục (Master Data Import)</h3>
                <button @click="showGlobalBulkModal = false" class="text-amber-700 hover:text-amber-900"><i class="fas fa-times"></i></button>
            </div>
            
            <div class="flex-1 overflow-y-auto p-6">
                <form action="{% url 'global_bulk_create' %}" method="POST" class="space-y-4">
                    {% csrf_token %}
                    <div class="bg-blue-50 border border-blue-100 text-blue-800 p-4 rounded-lg text-sm space-y-2">
                        <p class="font-bold"><i class="fas fa-info-circle mr-1"></i> Hướng dẫn nhập liệu một bước:</p>
                        <p>Sao chép dữ liệu từ Excel và dán vào ô bên dưới. Yêu cầu định dạng bảng gồm ít nhất 5 cột (cột 6,7 là tùy chọn). Các cột cách nhau bằng phím Tab (mặc định khi copy từ Excel).</p>
                        <div class="bg-white p-2 rounded border border-blue-200 font-mono text-xs overflow-x-auto">
                            Mã Trạm | Tên Trạm | Mã Ngăn lộ | Tên Ngăn lộ | Mã Rơ-le | Tên Rơ-le (Tùy chọn) | Hãng SX (Tùy chọn)
                        </div>
                        <p class="text-xs text-blue-600 italic">Hệ thống sẽ tự động đối chiếu: Nếu Trạm hoặc Ngăn lộ chưa tồn tại, hệ thống sẽ tự động tạo mới!</p>
                    </div>
                    <textarea name="raw_text" rows="12" required class="w-full p-3 border border-slate-300 rounded focus:border-amber-500 outline-none font-mono text-sm whitespace-pre text-nowrap overflow-auto bg-slate-50" placeholder="Mã Trạm&#9;Tên Trạm&#9;Mã Ngăn lộ&#9;Tên Ngăn lộ&#9;Mã Rơ-le..."></textarea>
                    
                    <div class="flex justify-end gap-2 pt-2">
                        <button type="button" @click="showGlobalBulkModal = false" class="px-4 py-2 text-sm text-slate-600 bg-slate-100 hover:bg-slate-200 rounded font-medium">Hủy</button>
                        <button type="submit" class="px-6 py-2 text-sm text-white bg-amber-600 hover:bg-amber-700 rounded shadow-sm font-bold"><i class="fas fa-upload mr-1"></i> Bắt đầu Nạp Dữ Liệu</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
"""

content = content.replace('</div>\n{% endblock %}', global_modal + '\n</div>\n{% endblock %}')

with open('d:/project/dien-luc/templates/stations/station_list.html', 'w', encoding='utf-8') as f:
    f.write(content)
