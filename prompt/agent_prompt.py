from utils.get_absolute_path import get_absolute_path


def get_prompt(**kwargs):
    _user_instruction = kwargs.get('user_instruction')
    _history = kwargs.get('history')
    _visible_elements = kwargs.get('visible_elements')
    path = get_absolute_path("/prompt/prompt_template.txt")
    with open(path, 'r') as f:
        content = f.read()
    content = content.format(user_command=_user_instruction, history=_history, visible_elements=_visible_elements)
    return content
