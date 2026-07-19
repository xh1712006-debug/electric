import re

with open('d:/project/dien-luc/templates/core/role_matrix.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the group header formatting
new_headers = '''
                        {% for group in groups %}
                        <th class="px-3 py-4 text-xs font-bold tracking-wider text-slate-700 text-center uppercase border-r border-slate-200 hover:bg-slate-200 transition-colors align-top min-w-[140px]">
                            <div class="flex flex-col items-center gap-2">
                                <span class="px-3 py-1.5 rounded bg-white border border-slate-200 shadow-sm text-evn-blue whitespace-nowrap text-[13px]">
                                    <i class="fas fa-user-shield mr-1 text-slate-400"></i> {{ group.vi_name }}
                                </span>
                            </div>
                        </th>
                        {% endfor %}
'''

pattern = re.compile(r'{%\s*for group in groups\s*%}.*?{%\s*endfor\s*%}', re.DOTALL)
# Since there are two loops over `groups` in the file (one for th, one for td)
# I will use a precise replace.

content = content.replace('''                        {% for group in groups %}
                        <th class="px-3 py-4 text-xs font-bold tracking-wider text-slate-700 text-center uppercase border-r border-slate-200 hover:bg-slate-200 transition-colors align-top min-w-[140px]">
                            <div class="flex flex-col items-center gap-2">
                                <span class="px-2.5 py-1 rounded-md bg-white border border-slate-200 shadow-sm text-evn-blue whitespace-nowrap">
                                    <i class="fas fa-user-shield mr-1 text-slate-400"></i> {{ group.name }}
                                </span>
                                <span class="text-[11px] text-slate-500 normal-case">{{ group.vi_name }}</span>
                            </div>
                        </th>
                        {% endfor %}''', new_headers)

with open('d:/project/dien-luc/templates/core/role_matrix.html', 'w', encoding='utf-8') as f:
    f.write(content)
