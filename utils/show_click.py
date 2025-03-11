
def show_click_position(page, x, y):
    # 注入 JavaScript，在页面上显示点击位置
    page.evaluate(f"""
        const dot = document.createElement('div');
        dot.style.position = 'absolute';
        dot.style.left = '{x}px';
        dot.style.top = '{y}px';
        dot.style.width = '10px';
        dot.style.height = '10px';
        dot.style.backgroundColor = 'red';
        dot.style.borderRadius = '50%';
        dot.style.zIndex = 10000;
        document.body.appendChild(dot);
    """)