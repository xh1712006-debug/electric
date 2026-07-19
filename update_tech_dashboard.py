import re

with open('d:/project/dien-luc/templates/core/dashboard_technician.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_content = '''{% extends "base.html" %}

{% block title %}KTV Dashboard | RMS{% endblock %}
{% block header_title %}Không gian Làm việc Kỹ Thuật Viên{% endblock %}

{% block content %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
    
    <!-- Card 1 -->
    <div class="bg-gradient-to-br from-white to-blue-50/50 rounded-2xl p-6 shadow-sm border border-slate-100/60 flex items-center justify-between hover:shadow-md hover:-translate-y-1 transition-all duration-300 group">
        <div>
            <p class="text-sm font-medium text-slate-500 mb-1 group-hover:text-blue-600 transition-colors">Việc Mới Nhận</p>
            <h3 class="text-3xl font-black text-slate-800 tracking-tight">{{ new_sheets }}</h3>
        </div>
        <div class="w-14 h-14 bg-gradient-to-br from-blue-50 to-blue-100 text-blue-600 rounded-2xl flex items-center justify-center text-2xl shadow-inner group-hover:rotate-12 transition-transform">
            <i class="fas fa-inbox"></i>
        </div>
    </div>
    
    <!-- Card 2 -->
    <div class="bg-gradient-to-br from-white to-amber-50/50 rounded-2xl p-6 shadow-sm border border-slate-100/60 flex items-center justify-between hover:shadow-md hover:-translate-y-1 transition-all duration-300 group">
        <div>
            <p class="text-sm font-medium text-slate-500 mb-1 group-hover:text-amber-600 transition-colors">Đang Xử Lý</p>
            <h3 class="text-3xl font-black text-slate-800 tracking-tight">{{ in_progress }}</h3>
        </div>
        <div class="w-14 h-14 bg-gradient-to-br from-amber-50 to-amber-100 text-amber-500 rounded-2xl flex items-center justify-center text-2xl shadow-inner group-hover:rotate-12 transition-transform">
            <i class="fas fa-tools"></i>
        </div>
    </div>
    
    <!-- Card 3 -->
    <div class="bg-gradient-to-br from-white to-emerald-50/50 rounded-2xl p-6 shadow-sm border border-slate-100/60 flex items-center justify-between hover:shadow-md hover:-translate-y-1 transition-all duration-300 group">
        <div>
            <p class="text-sm font-medium text-slate-500 mb-1 group-hover:text-emerald-600 transition-colors">Hoàn Thành (Của tôi)</p>
            <h3 class="text-3xl font-black text-slate-800 tracking-tight">{{ completed }}</h3>
        </div>
        <div class="w-14 h-14 bg-gradient-to-br from-emerald-50 to-emerald-100 text-emerald-500 rounded-2xl flex items-center justify-center text-2xl shadow-inner group-hover:rotate-12 transition-transform">
            <i class="fas fa-check-double"></i>
        </div>
    </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
    
    <!-- Checklist -->
    <div class="lg:col-span-2 bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
        <div class="flex items-center justify-between mb-6">
            <h3 class="text-lg font-bold text-slate-800 flex items-center gap-2"><i class="fas fa-tasks text-evn-blue"></i> Phiếu Cần Xử Lý Ngay</h3>
            <a href="{% url 'my_sheets' %}" class="text-sm font-medium text-blue-600 hover:text-blue-800">Mở toàn bộ &rarr;</a>
        </div>
        
        <div class="space-y-4">
            {% for sheet in recent_sheets %}
            <div class="p-4 rounded-xl border border-slate-100 bg-slate-50 hover:bg-white hover:shadow-sm hover:border-slate-200 transition-all flex items-center justify-between group">
                <div class="flex items-center gap-4">
                    <div class="w-10 h-10 rounded-full {% if sheet.status == 'TRANSFERRED' %}bg-blue-100 text-blue-600{% else %}bg-amber-100 text-amber-600{% endif %} flex items-center justify-center text-lg shadow-sm">
                        <i class="{% if sheet.status == 'TRANSFERRED' %}fas fa-file-download{% else %}fas fa-hard-hat{% endif %}"></i>
                    </div>
                    <div>
                        <a href="{% url 'sheet_detail' sheet.id %}" class="font-bold text-slate-800 hover:text-blue-600">{{ sheet.sheet_code }}</a>
                        <p class="text-xs text-slate-500 mt-0.5">{{ sheet.title|truncatechars:50 }}</p>
                    </div>
                </div>
                <div>
                    {% if sheet.status == 'TRANSFERRED' %}
                    <span class="px-3 py-1 bg-blue-50 text-blue-700 text-xs font-bold rounded-lg border border-blue-200 uppercase tracking-wider">Việc Mới</span>
                    {% else %}
                    <span class="px-3 py-1 bg-amber-50 text-amber-700 text-xs font-bold rounded-lg border border-amber-200 uppercase tracking-wider">Đang Làm</span>
                    {% endif %}
                </div>
            </div>
            {% empty %}
            <div class="text-center py-10 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                <div class="w-16 h-16 bg-slate-100 text-slate-300 rounded-full flex items-center justify-center text-3xl mx-auto mb-3">
                    <i class="fas fa-mug-hot"></i>
                </div>
                <h4 class="text-slate-600 font-semibold">Hiện tại bạn không có phiếu nào chờ xử lý</h4>
                <p class="text-sm text-slate-400 mt-1">Hãy nghỉ ngơi một chút nhé!</p>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <!-- Chart Section (Doughnut Chart) -->
    <div class="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col">
        <h3 class="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2"><i class="fas fa-chart-pie text-evn-blue"></i> Trạng thái Công việc</h3>
        <div class="h-64 w-full flex items-center justify-center relative flex-1">
            <canvas id="techPieChart"></canvas>
        </div>
    </div>
</div>

<!-- KTV Activity Section -->
<div class="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
    <div class="flex items-center justify-between mb-6">
        <h3 class="text-lg font-bold text-slate-800 flex items-center gap-2"><i class="fas fa-signature text-slate-400"></i> Lịch sử Ký số Của Tôi</h3>
    </div>
    <div class="space-y-6">
        {% for act in recent_activities %}
        <div class="flex gap-4 group">
            <div class="mt-1 relative">
                <div class="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-emerald-100 ring-4 z-10 relative"></div>
                {% if not forloop.last %}
                <div class="absolute top-3 left-1/2 -ml-px w-0.5 h-12 bg-slate-100"></div>
                {% endif %}
            </div>
            <div>
                <p class="text-sm text-slate-800 font-semibold group-hover:text-blue-600 transition-colors">Bạn đã ký xác nhận thi công Phiếu <a href="{% url 'sheet_detail' act.sheet.id %}" class="text-blue-600 hover:underline">#{{ act.sheet.sheet_code }}</a></p>
                <p class="text-[11px] text-slate-400 font-mono mt-1 break-all bg-slate-50 px-2 py-1 rounded border border-slate-100 inline-block">Hash: {{ act.signature_hash|truncatechars:30 }}</p>
                <p class="text-xs text-slate-400 mt-1.5 font-medium"><i class="far fa-clock mr-1"></i>{{ act.signed_at|timesince }} trước</p>
            </div>
        </div>
        {% empty %}
        <div class="text-center py-6 text-slate-500 text-sm italic">
            Bạn chưa thực hiện ký số Phiếu nào gần đây.
        </div>
        {% endfor %}
    </div>
</div>

<script>
document.addEventListener("DOMContentLoaded", function() {
    const doughnutData = {{ doughnut_data|safe }};
    
    // Doughnut Chart
    const ctxPie = document.getElementById('techPieChart').getContext('2d');
    new Chart(ctxPie, {
        type: 'doughnut',
        data: {
            labels: ['Việc Mới', 'Đang Làm', 'Đã Xong'],
            datasets: [{
                data: doughnutData,
                backgroundColor: [
                    '#3b82f6', // blue-500
                    '#f59e0b', // amber-500
                    '#10b981'  // emerald-500
                ],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { 
                    position: 'bottom',
                    labels: {
                        padding: 20,
                        usePointStyle: true,
                        font: { family: "'Inter', sans-serif" }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    padding: 12,
                    bodyFont: { size: 13, family: "'Inter', sans-serif" },
                    cornerRadius: 8,
                }
            },
            animation: { animateScale: true, animateRotate: true, duration: 1200 }
        }
    });
});
</script>
{% endblock %}
'''

with open('d:/project/dien-luc/templates/core/dashboard_technician.html', 'w', encoding='utf-8') as f:
    f.write(new_content)
