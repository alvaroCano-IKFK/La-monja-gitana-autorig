import maya.cmds as cmds
import guides_module
import controlsLibrary
import groups_module
import spine_module
import hip_module
import leg_module


class BodyModule(object): 
    """Este módulo se encarga de construir el cuerpo del rig, incluyendo la columna vertebral, cadera y piernas."""  
    def __init__(self, root_guide="root", 
                 rig_name="Character", 
                 root_instance=None,
                 thigh_guides=("L_hip", "R_hip"),
                 thigh_axes="xyz"):
        
        self.root_guide= root_guide
        self.rig_name= rig_name

        self.ctrl_style = "bodyControl"

        # Guias de los muslos. El body_CTL es el COG, y el COG va al pelvis:
        # centrado entre las dos piernas y a la altura de los muslos. Antes
        # salia de la guia "root" de la espina, asi que al subir la espina el
        # control se subia con ella y se quedaba por encima de la cadera.
        #
        # No hace falta ninguna guia nueva: las de los muslos ya existen
        # cuando corre este paso. El build llama a mirror_missing() antes de
        # empezar, asi que R_hip esta puesta aunque no se le haya dado a
        # MIRROR a mano.
        self.thigh_guides = tuple(thigh_guides)

        # Que ejes salen de los muslos. Por defecto los tres, que es el COG
        # clasico. Con "y" solo se coge la ALTURA y la X / Z se quedan en las
        # de la guia root, por si el personaje no esta centrado en el origen.
        self.thigh_axes = thigh_axes.lower()

        self.group_maker= groups_module.ControlsGroups()
        self.root_instance= root_instance

        self.body_ctl = None
        self.body_joint = None
        self.body_position = None
        

    def _body_position(self):
        """
        Donde va el body_CTL: el punto medio entre las dos guias de muslo.

        El COG tiene que quedar entre las piernas y a su altura, no donde
        empieza la espina. Como la espina puede subir o bajar sin que las
        piernas se muevan, la posicion se saca de los muslos y no de la guia
        root, que es lo que hacia antes.

        Con las dos guias sale el punto medio exacto: en un personaje
        simetrico eso da X = 0 (centrado) y la Y / Z del muslo.

        Si solo hay una pierna en la receta, se coge su altura y su
        profundidad pero la X se deja en la de la guia root: con una sola
        guia no hay forma de saber donde esta la linea media, y mandar el COG
        al muslo izquierdo seria peor que dejarlo donde estaba.

        Sin ninguna guia de muslo (un rig sin piernas) se vuelve a la guia
        root, que es el comportamiento de siempre.
        """
        # La guia root ya no es obligatoria: solo se usa para los ejes que NO
        # vengan de los muslos. Si no esta, se da por hecho el origen, que es
        # lo unico razonable sin nada contra lo que medir.
        has_root = cmds.objExists(self.root_guide)
        root_position = (cmds.xform(self.root_guide, q=True, ws=True, t=True)
                         if has_root else [0.0, 0.0, 0.0])

        found = [guide for guide in self.thigh_guides if cmds.objExists(guide)]

        if not found:
            if not has_root:
                cmds.error(f"[Body] No hay ni guias de muslo "
                           f"({', '.join(self.thigh_guides)}) ni guia "
                           f"'{self.root_guide}'. No hay de donde sacar la "
                           f"posicion del body_CTL.")

            cmds.warning(f"[Body] No encuentro las guias de muslo "
                         f"({', '.join(self.thigh_guides)}). El body_CTL se "
                         f"queda en '{self.root_guide}'.")
            return list(root_position), root_position

        positions = [cmds.xform(guide, q=True, ws=True, t=True)
                     for guide in found]

        midpoint = [sum(values) / float(len(values))
                    for values in zip(*positions)]

        # Con una sola guia el punto medio ES esa guia, asi que la X se
        # descarta: iria a parar al muslo en vez de a la linea media.
        axes = self.thigh_axes
        if len(found) == 1 and has_root:
            axes = axes.replace("x", "")
            cmds.warning(f"[Body] Solo encuentro {found[0]}. Se coge su "
                         f"altura, pero la X del body_CTL se queda en la de "
                         f"'{self.root_guide}'.")
        elif len(found) == 1:
            cmds.warning(f"[Body] Solo encuentro {found[0]} y no hay guia "
                         f"'{self.root_guide}'. El body_CTL se va al muslo, "
                         f"no a la linea media. Revisalo.")

        position = [
            midpoint[index] if axis in axes else root_position[index]
            for index, axis in enumerate("xyz")
        ]

        print(f"[Body] body_CTL en {tuple(round(value, 4) for value in position)} "
              f"desde {', '.join(found)} (ejes '{axes}').")

        return position, root_position

    def build(self):
        """Construye el cuerpo del rig a partir de las guías de los muslos."""

        pos_body, _pos_root = self._body_position()
        self.body_position = pos_body

        cmds.select(clear=True)
        body_joint = cmds.joint(n=f"{self.rig_name}_body_JNT", p=pos_body)

        #Control
        name = f"{self.rig_name}_body_CTL"
        bodyControl = controlsLibrary.create_control_from_lib(
            lib_name=self.ctrl_style, 
            final_name=name)
        # La jerarquia se sigue alineando con la guia root para quedarse con
        # su ORIENTACION, y despues se le pisa la traslacion con la posicion
        # de los muslos. Asi el control mira donde miraba y solo cambia de
        # sitio, que es lo unico que se pedia.
        #
        # Esto va ANTES de parentear nada debajo: cmds.parent es absoluto, asi
        # que lo que se cuelgue luego (los controles de la espina, el hip)
        # conserva su posicion de mundo y no se arrastra con el COG.
        bodyControl_off = self.group_maker.create_rig_hierarchy(bodyControl, self.root_guide)
        cmds.xform(bodyControl_off, ws=True, t=pos_body)

        cmds.parentConstraint(bodyControl, body_joint)

        self.localCtl = (
            f"{self.root_instance.rig_name}_local_CTL"
            if self.root_instance else None
        )
        if self.localCtl:
            cmds.parent(bodyControl_off, self.localCtl)
            
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(body_joint, rig_grp)

        if self.root_instance:
            self.root_instance.body_ctl = bodyControl  # ← expones el ctl al root_rig

        self.body_ctl = bodyControl
        self.body_joint = body_joint

        print("Body module built successfully.")

        return self