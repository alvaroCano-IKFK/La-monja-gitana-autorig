import maya.cmds as cmds

class Controls(object):
    def __init__(self, scale=1.0, color=None):
        self.scale = scale
        self.default_color = color
        self.prefix = "CTL"

    def set_color(self, ctrl, color_index):
        if color_index is not None:
            cmds.setAttr(f"{ctrl}.overrideEnabled", 1)
            cmds.setAttr(f"{ctrl}.overrideColor", color_index)

    def circle_ctl_builder(self, name="circle_ctl", radius=1.0, color=None):
        final_radius = radius * self.scale
        ctrl = cmds.circle(d=3, r=final_radius, n=name, nr=(0,1,0))[0]
        target_color = color if color is not None else self.default_color
        self.set_color(ctrl, target_color)
        return ctrl

    def square_ctl_builder(self, name="square_ctl", size=1.0, color=None):
        s = size * self.scale
        pts = [(-s,-s,-s), (s,-s,-s), (s,-s,s), (-s,-s,s), (-s,-s,-s),
               (-s,s,-s), (s,s,-s), (s,s,s), (-s,s,s), (-s,s,-s),
               (-s,s,s), (-s,-s,s), (s,-s,s), (s,s,s), (s,s,-s), (s,-s,-s)]
        ctrl = cmds.curve(d=1, p=pts, n=name)
        target_color = color if color is not None else self.default_color
        self.set_color(ctrl, target_color)
        return ctrl

    def gear_ctl_builder(self, name="gear_ctl", color=None):
        # 1. Creamos el engranaje temporal
        # s=8 y hd=2 para que coincida con los índices que me pasaste
        temp_results = cmds.polyGear(s=8, hd=2, r=1.0 * self.scale)
        temp_gear = temp_results[0]
        
        # 2. Definimos la lista de índices que forman la silueta (los que me diste)
        edge_indices = [
            57, 59, 61, 63, 65, 67, 70, 72, 74, 76, 78, 80, 
            83, 85, 87, 89, 91, 93, 96, 98, 100, 102, 104, 106, 
            109, 111, 113, 115, 117, 119, 122, 124, 126, 128, 130, 132, 
            135, 137, 139, 141, 143, 145, 148, 150, 152, 154, 156, 158
        ]
        
        # 3. Construimos los nombres de los componentes (ej: pGear1.e[57])
        edges_to_select = [f"{temp_gear}.e[{i}]" for i in edge_indices]
        
        # 4. Seleccionamos la lista completa
        cmds.select(edges_to_select)
        
        # 5. Convertimos a curva (degree=1 para mantener la forma dentada)
        gear_curve = cmds.polyToCurve(n=name, form=2, degree=1)[0]
        
        # 6. Limpieza profunda
        cmds.delete(temp_gear)
        cmds.delete(gear_curve, ch=True)
        
        # 7. Aplicar color
        target_color = color if color is not None else self.default_color
        self.set_color(gear_curve, target_color)
        
        return gear_curve
        
        
    def lollipop_ctl_builder(self, name="lollipop_ctl", size=0.5, color=None):
        # Aplicamos la escala
        s = size * self.scale
        
        # Definimos los puntos como una lista de tuplas (x, y, z)
        # He multiplicado las coordenadas por 's' para que el tamaño sea dinámico
        pts = [
            (0, 0, 3*s),   # Inicio base superior
            (-1*s, 0, 3*s), 
            (-1*s, 0, 5*s), 
            (1*s, 0, 5*s), 
            (1*s, 0, 3*s), 
            (0, 0, 3*s),   # Cierre cabeza superior
            (0, 0, -3*s),  # Bajada palo
            (-1*s, 0, -3*s), 
            (-1*s, 0, -5*s), 
            (1*s, 0, -5*s), 
            (1*s, 0, -3*s), 
            (0, 0, -3*s)   # Cierre cabeza inferior
        ]
        
        # Creamos la curva. d=1 significa que es lineal (recta)
        ctrl = cmds.curve(d=1, p=pts, n=name)
        
        # Aplicamos color
        target_color = color if color is not None else self.default_color
        self.set_color(ctrl, target_color)
        
        return ctrl
        
        
    def wave_ctl_builder(self, name="wave_ctl", radius=2, color=None):
        final_radius = radius * self.scale
        # Creamos el círculo y guardamos el nombre real en una variable
        results = cmds.circle(d=3, r=final_radius, n=name, nr=(0,1,0))
        wave_ctl = results[0]
        
        # En lugar de select, actuamos directamente sobre los CVs del objeto creado
        # Usamos valores más pequeños o normalizados para no "perder" el centro
        cmds.xform(f"{wave_ctl}.cv[3]", t=(-5, 2, 0), r=True, os=True)
        cmds.xform(f"{wave_ctl}.cv[7]", t=(5, 2, 0), r=True, os=True)
        
        # Escalar y mover otros CVs para dar forma sin alejar el pivote
        mid_cvs = [f"{wave_ctl}.cv[{i}]" for i in [0, 2, 4, 6]]
        cmds.xform(mid_cvs, t=(0, 1, 0), r=True, os=True)
    
        target_color = color if color is not None else self.default_color
        self.set_color(wave_ctl, target_color)
        
        return wave_ctl
        
# Para probarlo:
#wave = Controls(scale=2.0, color=17) # Amarillo por ejemplo
#wave.wave_ctl_builder()