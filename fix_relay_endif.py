import re

with open('d:/project/dien-luc/templates/stations/relay_status.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the endif tags that were supposed to be removed
content = content.replace('                    </div>\n                </div>\n                {% endif %}', '                    </div>\n                </div>')

with open('d:/project/dien-luc/templates/stations/relay_status.html', 'w', encoding='utf-8') as f:
    f.write(content)
