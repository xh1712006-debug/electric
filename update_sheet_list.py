import re

with open('d:/project/dien-luc/templates/sheets/sheet_list.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the static pagination with dynamic pagination
new_pagination = '''
    <!-- Pagination -->
    {% if sheets.has_other_pages %}
    <div class="px-6 py-4 border-t border-slate-100 flex items-center justify-between">
        <span class="text-sm text-slate-500">
            Hiển thị trang {{ sheets.number }} / {{ sheets.paginator.num_pages }}
        </span>
        <div class="flex gap-1">
            {% if sheets.has_previous %}
            <a href="?page={{ sheets.previous_page_number }}{% if search_query %}&q={{ search_query }}{% endif %}{% if status_filter %}&status={{ status_filter }}{% endif %}" class="px-3 py-1 border border-slate-300 rounded text-sm text-slate-600 hover:bg-slate-50">&laquo; Trước</a>
            {% endif %}
            
            {% for i in sheets.paginator.page_range %}
                {% if sheets.number == i %}
                <span class="px-3 py-1 bg-primary text-white rounded text-sm font-bold">{{ i }}</span>
                {% elif i > sheets.number|add:'-3' and i < sheets.number|add:'3' %}
                <a href="?page={{ i }}{% if search_query %}&q={{ search_query }}{% endif %}{% if status_filter %}&status={{ status_filter }}{% endif %}" class="px-3 py-1 border border-slate-300 rounded text-sm text-slate-600 hover:bg-slate-50">{{ i }}</a>
                {% endif %}
            {% endfor %}
            
            {% if sheets.has_next %}
            <a href="?page={{ sheets.next_page_number }}{% if search_query %}&q={{ search_query }}{% endif %}{% if status_filter %}&status={{ status_filter }}{% endif %}" class="px-3 py-1 border border-slate-300 rounded text-sm text-slate-600 hover:bg-slate-50">Sau &raquo;</a>
            {% endif %}
        </div>
    </div>
    {% endif %}
</div>
{% endblock %}
'''

# regex to replace from <!-- Pagination --> to the end of the file
pattern = re.compile(r'<!-- Pagination -->.*', re.DOTALL)
content = pattern.sub(new_pagination, content)

with open('d:/project/dien-luc/templates/sheets/sheet_list.html', 'w', encoding='utf-8') as f:
    f.write(content)
