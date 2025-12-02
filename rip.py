import tree_sitter_rust as tsrust
from tree_sitter import Language, Parser
import sys
import re
import os

def clean_space(text):
    """
    将多余的空白字符（换行、多空格）压缩为一个空格。
    """
    return re.sub(r'\s+', ' ', text).strip()

def get_node_text(node, source_code):
    return source_code[node.start_byte:node.end_byte].decode('utf-8')

def is_comment_or_attr(node):
    return node.type in ['line_comment', 'block_comment', 'attribute_item']

def get_function_signature(node, source_code):
    """
    提取函数签名，以分号结尾。
    """
    if node.type != 'function_item':
        return None

    sig_parts = []
    body_node = node.child_by_field_name('body')
    
    for child in node.children:
        if is_comment_or_attr(child):
            continue
        if body_node and child.id == body_node.id:
            break
        sig_parts.append(get_node_text(child, source_code))

    return clean_space(" ".join(sig_parts)) + ";"

def format_struct_or_enum(node, source_code):
    """
    提取 struct/enum，进入字段内部以去除注释。
    """
    # 1. 提取头部
    header_parts = []
    body_node = None
    
    for child in node.children:
        if child.type in ['field_declaration_list', 'enum_variant_list', 'ordered_field_declaration_list']:
            body_node = child
            break
        if not is_comment_or_attr(child) and child.type != ';':
            header_parts.append(get_node_text(child, source_code))
    
    header = clean_space(" ".join(header_parts))

    if not body_node:
        return header + ";"

    # 2. 处理字段
    fields = []
    is_tuple = (body_node.type == 'ordered_field_declaration_list')

    for child in body_node.children:
        if is_comment_or_attr(child):
            continue
        
        text = get_node_text(child, source_code)
        if text in [',', '{', '}', '(', ')']:
            continue
            
        if child.type in ['field_declaration', 'enum_variant']:
            f_parts = []
            for sub in child.children:
                if not is_comment_or_attr(sub):
                    f_parts.append(get_node_text(sub, source_code))
            fields.append(clean_space(" ".join(f_parts)))
        else:
            fields.append(clean_space(text))

    # 3. 组装
    if is_tuple:
        inner = ", ".join(fields)
        return f"{header}({inner});"
    else:
        inner = ",\n    ".join(fields)
        return f"{header} {{\n    {inner}\n}}"

def format_impl(node, source_code):
    """
    提取 impl 块。
    """
    header_parts = []
    body_node = node.child_by_field_name('body')

    if not body_node:
        return None

    for child in node.children:
        if child.id == body_node.id:
            break
        if not is_comment_or_attr(child):
            header_parts.append(get_node_text(child, source_code))
    
    header = clean_space(" ".join(header_parts))

    funcs = []
    for child in body_node.children:
        if is_comment_or_attr(child):
            continue
        
        if child.type == 'function_item':
            funcs.append(get_function_signature(child, source_code))
        elif child.type == 'const_item':
             c_parts = [get_node_text(c, source_code) for c in child.children if not is_comment_or_attr(c) and c.type != ';']
             line = clean_space(" ".join(c_parts))
             if not line.endswith(';'): line += ";"
             funcs.append(line)
        elif child.type == 'type_item':
             t_parts = [get_node_text(c, source_code) for c in child.children if not is_comment_or_attr(c)]
             funcs.append(clean_space(" ".join(t_parts)))
    
    if not funcs:
        return f"{header} {{ }}"
    
    inner = "\n    ".join(funcs)
    return f"{header} {{\n    {inner}\n}}"

def extract_signatures(file_path):
    LANGUAGE = Language(tsrust.language())
    parser = Parser(LANGUAGE)

    with open(file_path, 'rb') as f:
        source_code = f.read()

    tree = parser.parse(source_code)
    results = []

    def traverse(node):
        if node.type in ['struct_item', 'enum_item']:
            res = format_struct_or_enum(node, source_code)
            if res: results.append(res)
            return

        if node.type == 'impl_item':
            res = format_impl(node, source_code)
            if res: results.append(res)
            return 

        if node.type in ['source_file', 'mod_item']:
            for child in node.children:
                traverse(child)

    traverse(tree.root_node)
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 rip.py <path_to_rust_file>")
        sys.exit(1)

    try:
        file_path = sys.argv[1]
        
        # 获取相对路径
        try:
            rel_path = os.path.relpath(file_path)
        except ValueError:
            # 如果路径无法计算相对路径（例如跨盘符），则使用原路径
            rel_path = file_path

        signatures = extract_signatures(file_path)
        
        print("```rust")
        # 在代码块第一行输出文件标识
        print(f"// {rel_path}")
        print("") # 空一行
        
        for i, sig in enumerate(signatures):
            print(sig)
            if i < len(signatures) - 1:
                print("")
        print("```")
            
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")