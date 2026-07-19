import re
from html.parser import HTMLParser

class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if tag == 'style':
            self.in_style = True

    def handle_endtag(self, tag):
        if tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if not self.in_style and data.strip():
            self.text.append(data.strip())

def main():
    filepath = r"d:\project\dien-luc\TongHop_Spec_BaoCao.doc"
    outpath = r"d:\project\dien-luc\parsed_doc2.txt"
    
    try:
        with open(filepath, 'r', encoding='utf-16') as f:
            html_content = f.read()
    except UnicodeError:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()
            
    parser = MyHTMLParser()
    parser.feed(html_content)
    
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parser.text))
    print("Done")

if __name__ == "__main__":
    main()
