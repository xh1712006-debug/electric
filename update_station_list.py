import re

with open('d:/project/dien-luc/templates/stations/station_list.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_html = '''<div class="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden p-6" x-data="{ showStationModal: false, showBayModal: false, showRelayModal: false, showBulkModal: false, showGlobalBulkModal: false, activeStationId: null, activeBayId: null }">
    <div class="mb-6 flex justify-between items-center">
        <div>
            <h2 class="text-lg font-semibold text-slate-800">Danh sách Cây thư mục Thiết bị</h2>
            <p class="text-sm text-slate-500 mt-1">Quản lý phân cấp Trạm > Ngăn lộ > Rơ-le bảo vệ</p>
        </div>
        <div class="flex gap-2">
            <button @click="showGlobalBulkModal = true" class="px-4 py-2 bg-amber-500 text-white rounded-lg text-sm font-semibold hover:bg-amber-600 transition-colors shadow-sm border border-amber-600">
                <i class="fas fa-bolt mr-1"></i> Nhập Liệu Toàn Cục
            </button>
            <button @click="showStationModal = true" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">
                <i class="fas fa-plus mr-1"></i> Thêm Trạm mới
            </button>
        </div>
    </div>

    <!-- Thanh tìm kiếm Server-side -->
    <form method="GET" action="{% url 'station_list' %}" class="mb-6 flex gap-2 relative">
        <div class="relative flex-1">
            <i class="fas fa-search absolute left-3 top-3.5 text-slate-400 text-sm"></i>
            <input type="text" name="q" value="{{ q }}" 
                   hx-get="{% url 'search_suggestions' %}" 
                   hx-trigger="keyup changed delay:300ms, search" 
                   hx-target="#suggestions" 
                   list="suggestions"
                   autocomplete="off"
                   placeholder="Tìm kiếm Trạm, Ngăn lộ, Rơ-le (Ví dụ: REL_501)..." 
                   class="w-full pl-9 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:border-blue-500 focus:bg-white outline-none transition-colors text-sm shadow-sm">
            <datalist id="suggestions"></datalist>
        </div>
        <button type="submit" class="px-6 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-semibold shadow-sm hover:bg-blue-700 transition-colors">
            Tìm kiếm
        </button>
        {% if is_search %}
        <a href="{% url 'station_list' %}" class="px-4 py-2.5 bg-slate-200 text-slate-700 rounded-lg text-sm font-semibold hover:bg-slate-300 transition-colors flex items-center">
            Xóa lọc
        </a>
        {% endif %}
    </form>

    <div class="space-y-4">
        {% for station in stations %}
        <!-- Station Box -->
        <div class="border border-slate-200 rounded-lg overflow-hidden transition-all duration-300" 
             x-data="{ expandedStation: {{ 'true' if is_search else 'false' }}, loaded: {{ 'true' if is_search else 'false' }} }">
             
            <div class="bg-slate-50 px-4 py-3 flex justify-between items-center border-b border-slate-200 cursor-pointer hover:bg-slate-100 transition-colors" 
                 @click="
                    expandedStation = !expandedStation;
                    if(!loaded) {
                        htmx.ajax('GET', '{% url 'htmx_bays' station.id %}', {target: '#bays-{{ station.id }}', swap: 'innerHTML'});
                        loaded = true;
                    }">
                <div class="flex items-center">
                    <i class="fas fa-chevron-right text-slate-400 mr-3 text-sm transition-transform" :class="expandedStation ? 'rotate-90' : ''"></i>
                    <i class="fas fa-bolt text-yellow-500 mr-3 text-lg"></i>
                    <div>
                        <h3 class="font-bold text-slate-800">{{ station.station_name }}</h3>
                        <p class="text-xs text-slate-500 mt-1">Mã trạm: {{ station.station_code }} | Vị trí: {{ station.location|default:"-" }}</p>
                    </div>
                </div>
                <button @click.stop="activeStationId = {{ station.pk }}; showBayModal = true" class="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 hover:text-blue-600 hover:border-blue-400 rounded text-xs font-semibold transition-colors shadow-sm">
                    <i class="fas fa-plus mr-1"></i> Thêm Ngăn lộ
                </button>
            </div>
            
            <div class="p-4 bg-white space-y-4" x-show="expandedStation" style="display: none;">
                <div id="bays-{{ station.id }}" class="space-y-4">
                    {% if is_search %}
                        {% include 'stations/partials/bay_list.html' with bays=station.bays.all %}
                    {% else %}
                        <div class="text-center py-6 text-slate-400 htmx-indicator">
                            <i class="fas fa-spinner fa-spin text-2xl mb-2"></i>
                            <p class="text-sm">Đang tải danh sách Ngăn lộ...</p>
                        </div>
                    {% endif %}
                </div>
            </div>
        </div>
        {% empty %}
        <div class="text-center py-10 text-slate-500">
            <i class="fas fa-database text-4xl mb-3 text-slate-300"></i>
            <p>Không tìm thấy dữ liệu phù hợp.</p>
        </div>
        {% endfor %}
    </div>'''

# We need to replace the content between `<div class="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden p-6"` and `<!-- Modals -->`
pattern = re.compile(r'<div class="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden p-6".*?<!-- Modals -->', re.DOTALL)

new_content = pattern.sub(new_html + '\n\n    <!-- Modals -->', content)

with open('d:/project/dien-luc/templates/stations/station_list.html', 'w', encoding='utf-8') as f:
    f.write(new_content)
