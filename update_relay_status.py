import re

with open('d:/project/dien-luc/templates/stations/relay_status.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Update Alpine JS activeTab initialization
content = content.replace('x-data="{ activeTab: \'unconfigured\', searchCode: \'\' }"', 'x-data="{ activeTab: \'{{ active_tab }}\', searchCode: \'\' }"')

def get_pagination(obj, prefix, tab):
    html = f'''
                <!-- Pagination -->
                {{% if {obj}.has_other_pages %}}
                <div class="px-6 py-4 bg-white border-t border-slate-200 flex items-center justify-between">
                    <span class="text-sm text-slate-500">
                        Hiển thị trang {{{{ {obj}.number }}}} / {{{{ {obj}.paginator.num_pages }}}}
                    </span>
                    <div class="flex gap-1">
                        {{% if {obj}.has_previous %}}
                        <a href="?tab={tab}&page_{prefix}={{{{ {obj}.previous_page_number }}}}{{'{{'}} '&page_con='|add:configured_relays.number|stringformat:"s" if "{prefix}" == "unc" else '&page_unc='|add:unconfigured_relays.number|stringformat:"s" {{'}}'}}" class="px-3 py-1 border border-slate-300 rounded text-sm text-slate-600 hover:bg-slate-50">&laquo; Trước</a>
                        {{% endif %}}
                        
                        {{% for i in {obj}.paginator.page_range %}}
                            {{% if {obj}.number == i %}}
                            <span class="px-3 py-1 bg-blue-600 text-white rounded text-sm font-bold">{{{{ i }}}}</span>
                            {{% elif i > {obj}.number|add:'-3' and i < {obj}.number|add:'3' %}}
                            <a href="?tab={tab}&page_{prefix}={{{{ i }}}}{{'{{'}} '&page_con='|add:configured_relays.number|stringformat:"s" if "{prefix}" == "unc" else '&page_unc='|add:unconfigured_relays.number|stringformat:"s" {{'}}'}}" class="px-3 py-1 border border-slate-300 rounded text-sm text-slate-600 hover:bg-slate-50">{{{{ i }}}}</a>
                            {{% endif %}}
                        {{% endfor %}}
                        
                        {{% if {obj}.has_next %}}
                        <a href="?tab={tab}&page_{prefix}={{{{ {obj}.next_page_number }}}}{{'{{'}} '&page_con='|add:configured_relays.number|stringformat:"s" if "{prefix}" == "unc" else '&page_unc='|add:unconfigured_relays.number|stringformat:"s" {{'}}'}}" class="px-3 py-1 border border-slate-300 rounded text-sm text-slate-600 hover:bg-slate-50">Sau &raquo;</a>
                        {{% endif %}}
                    </div>
                </div>
                {{% endif %}}
'''
    return html

unc_pagination = get_pagination('unconfigured_relays', 'unc', 'unconfigured')
con_pagination = get_pagination('configured_relays', 'con', 'configured')

# We need to insert this after `</table>` for each tab.
# Unconfigured Tab
content = content.replace('                    </tbody>\n                </table>\n            </div>\n\n            <!-- Configured Tab -->', f'                    </tbody>\n                </table>\n{unc_pagination}            </div>\n\n            <!-- Configured Tab -->')

# Configured Tab
content = content.replace('                    </tbody>\n                </table>\n            </div>\n        </div>', f'                    </tbody>\n                </table>\n{con_pagination}            </div>\n        </div>')

with open('d:/project/dien-luc/templates/stations/relay_status.html', 'w', encoding='utf-8') as f:
    f.write(content)
