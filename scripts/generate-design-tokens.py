"""Generate CSS and the existing iOS named color assets from shared tokens."""
from pathlib import Path
import json
root=Path(__file__).resolve().parent.parent
tokens=json.loads((root/'shared/design-tokens.json').read_text())
css=[]
for mode,selector in [('light',':root'),('dark','html[data-theme=dark]')]:
    values=''.join(f'--{key}:{value};' for key,value in tokens[mode].items())
    if mode=='light':
        values+=''.join(f'--radius-{key}:{value}px;' for key,value in tokens['radii'].items())
        values+=''.join(f'--space-{value}:{value}px;' for value in tokens['spacing'])
        values+=''.join(f'--text-{key}:{value}px;' for key,value in tokens['typography'].items())
    css.append(selector+'{'+values+'}')
(root/'src/tokens.css').write_text('\n'.join(css)+'\n')
mapping={'AccentColor':'brand','CareBackground':'bg','CareSurface':'surface','CareInk':'ink','CareMint':'mint','CareRed':'red','CareYellow':'yellow','CareGreen':'green'}
assets=root/'ios/CareLink/Assets.xcassets'
def color(h):
    return {'color-space':'srgb','components':{'alpha':'1.000',**{k:format(int(h[i:i+2],16)/255,'.6f') for k,i in [('red',1),('green',3),('blue',5)]}}}
for name,token in mapping.items():
    folder=assets/(name+'.colorset');folder.mkdir(parents=True,exist_ok=True)
    colors=[{'idiom':'universal','color':color(tokens[mode][token]),**({'appearances':[{'appearance':'luminosity','value':'dark'}]} if mode=='dark' else {})} for mode in ['light','dark']]
    (folder/'Contents.json').write_text(json.dumps({'info':{'author':'xcode','version':1},'colors':colors},indent=2)+'\n')
print('Generated shared light/dark CSS and',len(mapping),'iOS named colors.')

# Platform layouts share values, while text on iOS follows Dynamic Type.
swift = ['// Generated from shared/design-tokens.json. Edit the source tokens instead.', 'import SwiftUI', '', 'enum CareDesign {']
for group, prefix in [('radii', 'Corner'), ('spacing', 'Space')]:
    swift.append('    enum '+prefix+' {')
    entries=tokens[group].items() if isinstance(tokens[group], dict) else [(f's{v}',v) for v in tokens[group]]
    swift.extend(f'        static let {key}: CGFloat = {value}' for key,value in entries)
    swift.append('    }')
swift.extend(['}', '', 'struct CareCard: ViewModifier {', '    func body(content: Content) -> some View {', '        content.padding(CareDesign.Space.s20)', '            .frame(maxWidth: .infinity, alignment: .leading)', '            .background(Color("CareSurface"), in: RoundedRectangle(cornerRadius: CareDesign.Corner.card, style: .continuous))', '    }', '}', 'extension View { func careCard() -> some View { modifier(CareCard()) } }', ''])
(root/'ios/CareLink/DesignTokens.swift').write_text('\n'.join(swift))
