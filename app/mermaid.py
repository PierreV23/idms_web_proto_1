COLORTABLE ={
    'black': '#000000',
    'gold2': '#EEC900',
    'skyblue1': '#87CEFF',
    'yellow': '#FFFF00'
}


class Mermaid:
    def __init__(self, type):
        self.graphtype = type
        self.graph_attr = {}
        self.nodes = []
        self.edges = []
        self.classes = []

    def node(self, name, label, shape='box', URL=None, fontsize=None, color='#000000', fillcolor='#ffffff', style=None, penwidth=1, setting=None, **kwargs):
        if not label:
            label = name
        label = f'"{label}"'
        if shape == 'box' or shape == 'box3d':
            nodedef = f'{name}({label})'
        elif shape == 'cds':
            nodedef = f'{name}[[{label}]]'
        elif shape == 'cylinder':
            nodedef = f'{name}[({label})]'
        elif shape == 'none':
            nodedef = f'{name}'
            self.classes.append(f'class {name} hidden')
        else:
            print(f'shape {shape}')
            nodedef = f'{name}[{label}]'
        self.nodes.append(nodedef)
        if URL:
            self.nodes.append(f'click {name} "{URL}"')
        if color.startswith('#'):
            lcolor = color
        else:
            lcolor = COLORTABLE.get(color, '#000000')
        if fillcolor.startswith('#'):
            fcolor = fillcolor
        else:
            fcolor = COLORTABLE.get(fillcolor, '#ffffff')
        for arg, value in kwargs.items():
            if arg == 'class':
                for val in value.split(' '):                    
                    self.classes.append(f'class {name} {val}')
        print(color, fillcolor)        
        self.nodes.append(f'style {name} fill:{fcolor}, stroke:{lcolor},stroke-width:{penwidth}px')

    def edge(self, left, right, style=None):
        if style is None:
            linedef = '-->'
        elif style == 'dashed':
            linedef = '-.->'
        else:
            print(f'STYLE {style}')
            linedef = '---'
        self.edges.append(f'{left} {linedef} {right}')

    def direction(self):
        return self.graph_attr.get('rankdir', 'TB')

    def pipe(self, **kwargs):
        # Ignore format
        result = ['<pre class="mermaid">']
        if self.graphtype == 'datagraph':
            result.append(f'flowchart {self.direction()}')
        result.extend(self.nodes)
        result.extend(self.edges)
        result.extend(self.classes)
        result.append('</pre>')
        return '\n'.join(result).encode('utf-8')





