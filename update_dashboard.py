import re

with open('d:/project/dien-luc/templates/core/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_content = '''{% extends "base.html" %}

{% block title %}Dashboard | RMS{% endblock %}
{% block header_title %}Tổng quan Hệ thống RMS{% endblock %}

{% block content %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
    
    <!-- Card 1 -->
    <div class="bg-gradient-to-br from-white to-slate-50 rounded-2xl p-6 shadow-sm border border-slate-100/60 flex items-center justify-between hover:shadow-md hover:-translate-y-1 transition-all duration-300 group">
        <div>
            <p class="text-sm font-medium text-slate-500 mb-1 group-hover:text-blue-600 transition-colors">Tổng số Phiếu</p>
            <h3 class="text-3xl font-black text-slate-800 tracking-tight">{{ total_sheets }}</h3>
        </div>
        <div class="w-14 h-14 bg-gradient-to-br from-blue-50 to-blue-100 text-blue-600 rounded-2xl flex items-center justify-center text-2xl shadow-inner group-hover:rotate-12 transition-transform">
            <i class="fas fa-file-alt"></i>
        </div>
    </div>
    
    <!-- Card 2 -->
    <div class="bg-gradient-to-br from-white to-slate-50 rounded-2xl p-6 shadow-sm border border-slate-100/60 flex items-center justify-between hover:shadow-md hover:-translate-y-1 transition-all duration-300 group">
        <div>
            <p class="text-sm font-medium text-slate-500 mb-1 group-hover:text-slate-700 transition-colors">Phiếu Đang Soạn</p>
            <h3 class="text-3xl font-black text-slate-800 tracking-tight">{{ draft_sheets }}</h3>
        </div>
        <div class="w-14 h-14 bg-gradient-to-br from-slate-100 to-slate-200 text-slate-600 rounded-2xl flex items-center justify-center text-2xl shadow-inner group-hover:rotate-12 transition-transform">
            <i class="fas fa-pen-nib"></i>
        </div>
    </div>
    
    <!-- Card 3 -->
    <div class="bg-gradient-to-br from-white to-amber-50/30 rounded-2xl p-6 shadow-sm border border-slate-100/60 flex items-center justify-between hover:shadow-md hover:-translate-y-1 transition-all duration-300 group">
        <div>
            <p class="text-sm font-medium text-slate-500 mb-1 group-hover:text-amber-600 transition-colors">Chờ Duyệt Ký số</p>
            <h3 class="text-3xl font-black text-slate-800 tracking-tight">{{ pending_review }}</h3>
        </div>
        <div class="w-14 h-14 bg-gradient-to-br from-amber-50 to-amber-100 text-amber-500 rounded-2xl flex items-center justify-center text-2xl shadow-inner group-hover:rotate-12 transition-transform">
            <i class="fas fa-clock"></i>
        </div>
    </div>
    
    <!-- Card 4 -->
    <div class="bg-gradient-to-br from-white to-emerald-50/30 rounded-2xl p-6 shadow-sm border border-slate-100/60 flex items-center justify-between hover:shadow-md hover:-translate-y-1 transition-all duration-300 group">
        <div>
            <p class="text-sm font-medium text-slate-500 mb-1 group-hover:text-emerald-600 transition-colors">Đã Hoàn Thành</p>
            <h3 class="text-3xl font-black text-slate-800 tracking-tight">{{ completed_sheets }}</h3>
        </div>
        <div class="w-14 h-14 bg-gradient-to-br from-emerald-50 to-emerald-100 text-emerald-500 rounded-2xl flex items-center justify-center text-2xl shadow-inner group-hover:rotate-12 transition-transform">
            <i class="fas fa-check-circle"></i>
        </div>
    </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
    <!-- Chart Section (Bar Chart) -->
    <div class="lg:col-span-2 bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
        <h3 class="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2"><i class="fas fa-chart-bar text-evn-blue"></i> Khối lượng Phiếu (7 ngày qua)</h3>
        <div class="h-72 w-full">
            <canvas id="barChart"></canvas>
        </div>
    </div>
    
    <!-- Chart Section (Doughnut Chart) -->
    <div class="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
        <h3 class="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2"><i class="fas fa-chart-pie text-evn-blue"></i> Tỷ lệ Trạng thái Phiếu</h3>
        <div class="h-64 w-full flex items-center justify-center relative">
            <canvas id="pieChart"></canvas>
            <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none mt-4">
                <span class="text-3xl font-black text-slate-800">{{ total_sheets }}</span>
                <span class="text-xs text-slate-500 font-medium">TỔNG</span>
            </div>
        </div>
    </div>
</div>

<!-- Activity Section -->
<div class="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
    <div class="flex items-center justify-between mb-6">
        <h3 class="text-lg font-bold text-slate-800 flex items-center gap-2"><i class="fas fa-history text-slate-400"></i> Hoạt động Ký số gần đây</h3>
        <a href="#" class="text-sm font-medium text-blue-600 hover:text-blue-800">Xem tất cả &rarr;</a>
    </div>
    <div class="space-y-6">
        {% for act in recent_activities %}
        <div class="flex gap-4 group">
            <div class="mt-1 relative">
                <div class="w-2.5 h-2.5 rounded-full {% if act.role == 'A0_A1' %}bg-blue-500 ring-blue-100{% elif act.role == 'SUPERVISOR' %}bg-emerald-500 ring-emerald-100{% else %}bg-amber-500 ring-amber-100{% endif %} ring-4 z-10 relative"></div>
                {% if not forloop.last %}
                <div class="absolute top-3 left-1/2 -ml-px w-0.5 h-12 bg-slate-100"></div>
                {% endif %}
            </div>
            <div>
                <p class="text-sm text-slate-800 font-semibold group-hover:text-blue-600 transition-colors">{{ act.role }} ký xác nhận Phiếu <a href="{% url 'sheet_detail' act.sheet.id %}" class="text-blue-600 hover:underline">#{{ act.sheet.sheet_code }}</a></p>
                <p class="text-xs text-slate-500 mt-0.5"><i class="fas fa-user-edit mr-1 text-slate-400"></i>{{ act.signer_name }} đã đóng mộc điện tử thành công.</p>
                <p class="text-xs text-slate-400 mt-1.5 font-medium"><i class="far fa-clock mr-1"></i>{{ act.signed_at|timesince }} trước</p>
            </div>
        </div>
        {% empty %}
        <div class="text-center py-6 text-slate-500 text-sm italic">
            Chưa có hoạt động ký số nào trên hệ thống.
        </div>
        {% endfor %}
    </div>
</div>

<script>
document.addEventListener("DOMContentLoaded", function() {
    // Data from Django
    const labels = {{ chart_labels|safe }};
    const data = {{ chart_data|safe }};
    const doughnutData = {{ doughnut_data|safe }};
    
    // Bar Chart
    const ctxBar = document.getElementById('barChart').getContext('2d');
    new Chart(ctxBar, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Số lượng Phiếu tạo mới',
                data: data,
                backgroundColor: 'rgba(59, 130, 246, 0.85)', // Blue-500
                hoverBackgroundColor: 'rgba(37, 99, 235, 1)', // Blue-600
                borderRadius: 6,
                barThickness: 32,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    padding: 12,
                    titleFont: { size: 13, family: "'Inter', sans-serif" },
                    bodyFont: { size: 14, family: "'Inter', sans-serif", weight: 'bold' },
                    displayColors: false,
                    cornerRadius: 8,
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#f1f5f9', drawBorder: false },
                    border: { display: false },
                    ticks: { precision: 0, color: '#64748b', padding: 10 }
                },
                x: {
                    grid: { display: false, drawBorder: false },
                    border: { display: false },
                    ticks: { color: '#64748b', padding: 10, font: { weight: '500' } }
                }
            },
            animation: { duration: 1000, easing: 'easeOutQuart' }
        }
    });

    // Doughnut Chart
    const ctxPie = document.getElementById('pieChart').getContext('2d');
    new Chart(ctxPie, {
        type: 'doughnut',
        data: {
            labels: ['Bản nháp', 'Đang thực hiện', 'KTV Đã ký', 'Chờ Duyệt A0/A1', 'Đã Hoàn Thành'],
            datasets: [{
                data: doughnutData,
                backgroundColor: [
                    '#e2e8f0', // slate-200
                    '#c084fc', // purple-400
                    '#f59e0b', // amber-500
                    '#f97316', // orange-500
                    '#10b981'  // emerald-500
                ],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: { display: false },
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

with open('d:/project/dien-luc/templates/core/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(new_content)
