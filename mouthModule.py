import maya.cmds as cmds

from groups_module import ControlsGroups

try:
    import controlsLibrary
except ImportError:
    controlsLibrary = None


class SimpleMouthModule(object):
    """
    Boca sin curvas, sin NURBS y sin nodos de geometria.

    Todo el sistema son joints, controles y parentConstraints con pesos. No hay
    motionPath, ni uvPin, ni closestPointOnSurface, ni composeMatrix, ni
    aimMatrix. Es a proposito: esta pensado como base minima sobre la que ir
    anadiendo capas y poder aislar que hace cada una.

    LA CADENA
    ---------
    Por cada mitad (upper y lower) y por cada lado hay cuatro posiciones, que
    salen de las guias:

        mid ---- in01 ---- in02 ---- comisura
                (levator   (pinch
                 depresor)

    Y se cuelgan asi:

        midMain       parentConstraint 100% al control del jaw de su mitad
        midSub        hijo del midMain en jerarquia, libre para el animador
        in01          parentConstraint  midMain 75% / comisura 25%
        in02          parentConstraint  midMain 25% / comisura 75%
        comisura      parentConstraint  jawUpper / jawLower segun UpperLower

    Por que no puede flipar: ningun control saca su orientacion de la forma de
    una curva ni de una superficie. Un parentConstraint mezcla dos transforms
    que ya existen, y con interpType Shortest esa mezcla es un slerp, que es
    continuo por construccion.
    """

    # base_name -> peso del MID (la comisura se lleva 1 - peso)
    CHAIN_WEIGHTS = {
        "01": 0.75,
        "02": 0.25,
    }

    # Como se llama cada eslabon en cada mitad
    CHAIN_NAMES = {
        "Upper": {"01": "levator", "02": "upperPinch"},
        "Lower": {"01": "depresor", "02": "lowerPinch"},
    }

    def __init__(self, rig_name="Character", root_instance=None,
                 lip_mid="C_lip_mid", lip_end="L_lip_end",
                 lip_in01="L_lip_in01", lip_in02="L_lip_in02",
                 jaw_upper_ctrl=None, jaw_lower_ctrl=None,
                 sides=("L", "R"), control_size=0.6):

        self.rig_name = rig_name
        self.root_instance = root_instance
        self.groups = ControlsGroups()

        # Guias. Solo existen en +X; el lado R se saca espejando la X.
        self.lip_mid = lip_mid
        self.lip_end = lip_end
        self.lip_in01 = lip_in01
        self.lip_in02 = lip_in02

        # Controles del jaw. Si no se pasan, se buscan por convencion.
        self.jaw_upper_ctrl = jaw_upper_ctrl or f"C_{rig_name}_jawUpper_CTRL"
        self.jaw_lower_ctrl = jaw_lower_ctrl or f"C_{rig_name}_jawLower_CTRL"

        self.sides = sides
        self.control_size = control_size

        # Reparto de la comisura entre las dos mitades de la mandibula.
        # 0.5 = parentConstraint al 50% entre jawUpper y jawLower, que es lo
        # que hace que al abrir la boca la comisura se quede a medio camino en
        # vez de irse entera con el labio de abajo.
        self.corner_upper_lower = 0.5

        # A True añade un atributo 'UpperLower' animable en el control de la
        # comisura, conectado a los dos pesos con un reverse. Es una capa mas,
        # asi que por defecto va apagado: los pesos se quedan fijos al 50%.
        self.corner_upper_lower_attr = False

        self.controls = {}
        self.joints = {}
        self.module_group = None

        # Grupos que hay que enganchar al jaw. Se guardan porque el jaw puede
        # construirse DESPUES que la boca, y entonces attach_to_jaw() se llama
        # mas tarde (lo hace build_module desde _build_jaw).
        self.mid_groups = {}
        self.corner_groups = {}
        self.attached_to_jaw = False

        # Control general de la boca.
        self.master_ctrl = None
        self.jaw_drivers = {}

    # ------------------------------------------------------------------
    # UTILIDADES
    # ------------------------------------------------------------------
    def _guide_transform(self, guide, side):
        """
        Posicion Y orientacion mundiales de una guia, espejadas si el lado es R.

        Las guias solo se crean en +X; el lado R se saca espejando en el plano
        YZ. La posicion es trivial (negar la X), pero la orientacion no: hay
        que espejar el comportamiento, no solo copiar los angulos.

        Se hace con el truco del grupo de escala negativa en vez de a mano:
        se mete un transform con la matriz de la guia dentro de un grupo con
        scaleX = -1 y se lee su resultado en mundo. Eso da exactamente el mismo
        espejo que mirrorJoint -myz -mb, y funciona con cualquier orientacion
        de guia, no solo con las que llevan un rotateY suelto.

        Devuelve (posicion, rotacion) o (None, None).
        """
        if not cmds.objExists(guide):
            cmds.warning(f"[SimpleMouth] No existe la guia '{guide}'.")
            return None, None

        position = cmds.xform(guide, q=True, ws=True, t=True)
        rotation = cmds.xform(guide, q=True, ws=True, ro=True)

        if side != "R":
            return position, rotation

        world_matrix = cmds.xform(guide, q=True, ws=True, matrix=True)

        mirror_group = cmds.group(em=True, n="tempMirrorGRP")
        cmds.setAttr(f"{mirror_group}.scaleX", -1)

        temp = cmds.group(em=True, n="tempMirrorTRN", parent=mirror_group)
        cmds.xform(temp, matrix=world_matrix)

        position = cmds.xform(temp, q=True, ws=True, t=True)
        rotation = cmds.xform(temp, q=True, ws=True, ro=True)

        cmds.delete(mirror_group)

        return position, rotation

    def _make_control(self, name, position, rotation=None, normal=(0, 0, 1)):
        """
        Un control en una posicion, con su jerarquia GRP/SPC/OFF/SDK/ANIM.

        Devuelve (control, grupo_raiz). Se usa controlsLibrary si esta; si no,
        un circulo, para que el modulo se pueda probar suelto.
        """
        if cmds.objExists(name):
            cmds.delete(name)

        control = None
        if controlsLibrary is not None:
            try:
                control = controlsLibrary.create_control_from_lib(
                    lib_name="circle", final_name=name
                )
            except Exception:
                control = None

        if control is None:
            control = cmds.circle(n=name, nr=normal, r=self.control_size,
                                  ch=False)[0]

        # Un locator temporal como destino del match: create_rig_hierarchy
        # espera un nodo, no una posicion.
        target = cmds.spaceLocator(n=f"{name}_tempTarget")[0]
        cmds.xform(target, ws=True, t=position)
        if rotation is not None:
            cmds.xform(target, ws=True, ro=rotation)

        # match_rotation a True: los controles (y con ellos sus joints) heredan
        # la orientacion de la guia. Antes salian alineados al mundo y no
        # coincidian con las guias, que es lo que se veia.
        group = self.groups.create_rig_hierarchy(
            control, target, match_rotation=rotation is not None,
            world_space=True
        )

        cmds.delete(target)

        return control, group

    def _make_joint(self, name, control):
        """
        Joint en la posicion del control y constreñido a el.

        parentConstraint y scaleConstraint: el joint es un pasajero del control
        y no tiene vida propia.
        """
        if cmds.objExists(name):
            cmds.delete(name)

        cmds.select(clear=True)
        joint = cmds.joint(n=name)
        cmds.matchTransform(joint, control, pos=True, rot=True)

        cmds.parentConstraint(control, joint, mo=False)
        cmds.scaleConstraint(control, joint, mo=False)

        cmds.select(clear=True)

        return joint

    def _blend_constraint(self, driver_a, driver_b, target, weight_a):
        """
        parentConstraint de dos targets con pesos, en Shortest.

        interpType 2 (Shortest) no es opcional: el valor por defecto (Average)
        promedia angulos de Euler, y promediar 179 con -179 da 0 en vez de 180.
        Ahi es donde salen los saltos.
        """
        constraint = cmds.parentConstraint(driver_a, driver_b, target, mo=True)[0]

        aliases = cmds.parentConstraint(constraint, q=True, weightAliasList=True)
        cmds.setAttr(f"{constraint}.{aliases[0]}", weight_a)
        cmds.setAttr(f"{constraint}.{aliases[1]}", 1.0 - weight_a)
        cmds.setAttr(f"{constraint}.interpType", 2)

        return constraint

    # ------------------------------------------------------------------
    # CONSTRUCCION
    # ------------------------------------------------------------------
    def _build_mid(self, half):
        """
        Los dos controles del centro de un labio, en jerarquia.

        midMain lo conduce el jaw al 100%; midSub cuelga de el y es el que toca
        el animador. Separarlos es lo que permite que el labio siga a la
        mandibula sin que el animador pierda sus canales: si el jaw escribiera
        sobre el mismo control que el animador anima, se pisarian.
        """
        position, rotation = self._guide_transform(self.lip_mid, "L")
        if position is None:
            return None, None

        main_name = f"C_{self.rig_name}_lip{half}Mid_CTRL"
        sub_name = f"C_{self.rig_name}_lip{half}MidSub_CTRL"

        main_ctrl, main_grp = self._make_control(main_name, position, rotation)
        sub_ctrl, sub_grp = self._make_control(sub_name, position, rotation)

        # El sub cuelga del main: jerarquia de verdad, no constraint.
        cmds.parent(sub_grp, main_ctrl)

        self.mid_groups[half] = main_grp

        self.controls[f"{half}MidMain"] = main_ctrl
        self.controls[f"{half}MidSub"] = sub_ctrl

        self._make_joint(f"C_{self.rig_name}_lip{half}Mid_JNT", sub_ctrl)

        return main_ctrl, sub_ctrl

    def _build_corner(self, side):
        """
        La comisura. Es el segundo padre de toda la cadena, asi que se
        construye antes que los eslabones.

        Se cuelga entre los dos controles del jaw con un atributo UpperLower,
        que es lo que hace que al abrir la boca la comisura se quede a medio
        camino en vez de irse entera con la mandibula.
        """
        position, rotation = self._guide_transform(self.lip_end, side)
        if position is None:
            return None

        name = f"{side}_{self.rig_name}_lipCorner_CTRL"
        control, group = self._make_control(name, position, rotation)

        self.corner_groups[side] = group

        self.controls[f"{side}Corner"] = control
        self._make_joint(f"{side}_{self.rig_name}_lipCorner_JNT", control)

        return control

    def _build_chain_link(self, half, side, key, mid_ctrl, corner_ctrl):
        """
        Un eslabon intermedio: control, joint y el constraint de dos padres.
        """
        guide = self.lip_in01 if key == "01" else self.lip_in02
        position, rotation = self._guide_transform(guide, side)
        if position is None:
            return None

        base_name = self.CHAIN_NAMES[half][key]
        name = f"{side}_{self.rig_name}_{base_name}_CTRL"

        control, group = self._make_control(name, position, rotation)

        weight = self.CHAIN_WEIGHTS[key]
        self._blend_constraint(mid_ctrl, corner_ctrl, group, weight)

        print(f"[SimpleMouth] {group}: {mid_ctrl} {weight:.2f} / "
              f"{corner_ctrl} {1.0 - weight:.2f}")

        self.controls[f"{side}{base_name}"] = control
        self._make_joint(f"{side}_{self.rig_name}_{base_name}_JNT", control)

        return control

    def _setup_jaw_driver(self, half, jaw_ctrl):
        """
        El transform que repite al control del jaw, pero colgando del general.

        Son DOS nodos, no uno, y el de arriba es el que arregla el pivote:

            mouthAll_CTRL
              |- jaw<half>DriverOffset_TRN   <- matchTransform al PADRE del
              |                                 control del jaw, sin conexiones
              |- jaw<half>Driver_TRN         <- connectAttr desde el control

        Por que hace falta el offset. El driver copia los canales LOCALES del
        control del jaw con conexiones directas. Si colgara del general a pelo,
        su mundo seria (general) x (local del jaw), y como el jaw en reposo
        tiene los canales a cero, el driver acabaria en la posicion del
        general, o sea en la boca. Al rotar la mandibula, la boca giraria
        alrededor de si misma en vez de alrededor del pivote del jaw.

        Con el offset puesto a la matriz del PADRE del control del jaw, el
        driver vale (general) x (padre del jaw) x (local del jaw), que es
        (general) x (mundo del jaw). El pivote vuelve a ser el de la mandibula
        y el general sigue desplazandolo todo.
        """
        offset_name = f"C_{self.rig_name}_jaw{half}DriverOffset_TRN"
        driver_name = f"C_{self.rig_name}_jaw{half}Driver_TRN"

        for node in (driver_name, offset_name):
            if cmds.objExists(node):
                cmds.delete(node)

        offset = cmds.group(em=True, n=offset_name, parent=self.master_ctrl)
        driver = cmds.group(em=True, n=driver_name, parent=offset)

        self.jaw_drivers[half] = driver

        if not cmds.objExists(jaw_ctrl):
            # El jaw aun no existe. Los nodos quedan creados y attach_to_jaw()
            # los coloca y conecta cuando la mandibula este construida.
            return driver

        parent = cmds.listRelatives(jaw_ctrl, parent=True, type="transform")
        reference = parent[0] if parent else jaw_ctrl
        cmds.matchTransform(offset, reference, pos=True, rot=True)

        for channel in ("translate", "rotate", "scale"):
            cmds.connectAttr(f"{jaw_ctrl}.{channel}",
                             f"{driver}.{channel}", force=True)

        return driver

    def _build_master(self):
        """
        Control general que mueve la boca entera.

        EL PROBLEMA QUE HAY QUE ESQUIVAR
        --------------------------------
        Un parentConstraint compensa SIEMPRE la matriz del padre del nodo que
        constriñe. Asi que meter un control por encima de los grupos y
        emparentarlo todo debajo no hace absolutamente nada: el constraint
        deshace el movimiento del padre y los controles se quedan clavados
        donde los pone el jaw. Es el error tipico y no da ningun aviso.

        LA SALIDA
        ---------
        Lo que si cuenta es la matriz del DRIVER. Asi que en vez de constreñir
        los grupos a los controles del jaw directamente, se constriñen a dos
        transforms intermedios que cuelgan del control general:

            mouthAll_CTRL
              |- jawUpperDriver_TRN   <- connectAttr desde jawUpper_CTRL
              |- jawLowerDriver_TRN   <- connectAttr desde jawLower_CTRL

        Los drivers copian los canales del jaw con conexiones DIRECTAS, no con
        constraint. Esa es la diferencia: una conexion directa escribe valores
        locales y no compensa nada, asi que el driver acaba en
        (transform del control general) x (transform local del jaw). Mueves el
        control general y se mueve toda la boca; mueves el jaw y sigue
        funcionando igual que antes.
        """
        name = f"C_{self.rig_name}_mouthAll_CTRL"

        position, rotation = self._guide_transform(self.lip_mid, "L")
        if position is None:
            return None

        control, group = self._make_control(name, position, rotation)
        self.master_ctrl = control
        self.controls["mouthAll"] = control

        self.jaw_drivers = {}
        for half, jaw_ctrl in (("Upper", self.jaw_upper_ctrl),
                               ("Lower", self.jaw_lower_ctrl)):
            self._setup_jaw_driver(half, jaw_ctrl)

        return control

    def attach_to_jaw(self):
        """
        Engancha la boca a la mandibula. Separado de build() a proposito.

        El orden de la receta puede construir la boca antes que el jaw, y estos
        constraints necesitan que los controles del jaw ya existan. build() lo
        intenta igual por si el jaw ya estaba; si no, build_module vuelve a
        llamar aqui desde _build_jaw.

        Es idempotente: si ya se engancho, no hace nada.
        """
        if self.attached_to_jaw:
            return True

        if not (cmds.objExists(self.jaw_upper_ctrl)
                and cmds.objExists(self.jaw_lower_ctrl)):
            return False

        # Los drivers se crearon vacios si el jaw no existia todavia. Se
        # rehacen enteros ahora que si: hay que recolocar el offset, y eso se
        # tiene que hacer antes de conectar nada.
        if self.master_ctrl:
            for half, jaw_ctrl in (("Upper", self.jaw_upper_ctrl),
                                   ("Lower", self.jaw_lower_ctrl)):
                driver = self.jaw_drivers.get(half)
                if driver and cmds.objExists(driver) and cmds.listConnections(
                        f"{driver}.rotate", s=True, d=False):
                    continue
                self._setup_jaw_driver(half, jaw_ctrl)

        upper_driver = self.jaw_drivers.get("Upper") or self.jaw_upper_ctrl
        lower_driver = self.jaw_drivers.get("Lower") or self.jaw_lower_ctrl

        # 1. Cada centro de labio, al 100% a su mitad de la mandibula.
        for half, group in self.mid_groups.items():
            if not group or not cmds.objExists(group):
                continue
            jaw_ctrl = upper_driver if half == "Upper" else lower_driver
            cmds.parentConstraint(jaw_ctrl, group, mo=True)
            print(f"[SimpleMouth] {group} <- {jaw_ctrl} (100%)")

        # 2. Las comisuras, entre las dos mitades, con su atributo animable.
        for side, group in self.corner_groups.items():
            if not group or not cmds.objExists(group):
                continue

            control = self.controls.get(f"{side}Corner")
            constraint = self._blend_constraint(
                upper_driver, lower_driver, group,
                1.0 - self.corner_upper_lower
            )

            if self.corner_upper_lower_attr:
                if not cmds.objExists(f"{control}.UpperLower"):
                    cmds.addAttr(control, ln="UpperLower", at="double",
                                 min=0, max=1, dv=self.corner_upper_lower,
                                 k=True)

                aliases = cmds.parentConstraint(constraint, q=True,
                                                weightAliasList=True)
                reverse = cmds.createNode(
                    "reverse",
                    n=f"{side}_{self.rig_name}_lipCornerUpperLower_REV"
                )
                cmds.connectAttr(f"{control}.UpperLower", f"{reverse}.inputX")
                cmds.connectAttr(f"{reverse}.outputX",
                                 f"{constraint}.{aliases[0]}")
                cmds.connectAttr(f"{control}.UpperLower",
                                 f"{constraint}.{aliases[1]}")

            weight = 1.0 - self.corner_upper_lower
            print(f"[SimpleMouth] {group} <- {upper_driver} "
                  f"{weight:.2f} / {lower_driver} "
                  f"{self.corner_upper_lower:.2f}")

        self.attached_to_jaw = True

        return True

    def build(self):
        group_name = f"C_{self.rig_name}_mouth_GRP"
        if cmds.objExists(group_name):
            cmds.delete(group_name)

        self.controls = {}
        self.joints = {}

        # 0. El control general. Va el primero porque los drivers del jaw
        #    cuelgan de el y todo lo demas se constriñe contra esos drivers.
        self._build_master()

        # 1. Los centros de los dos labios. Son el primer padre de la cadena.
        mid_controls = {}
        for half in ("Upper", "Lower"):
            main_ctrl, _ = self._build_mid(half)
            mid_controls[half] = main_ctrl

        # 2. Las comisuras. Segundo padre, compartidas por las dos mitades.
        corner_controls = {}
        for side in self.sides:
            corner_controls[side] = self._build_corner(side)

        # 3. Los eslabones, que ya solo cuelgan de los dos anteriores.
        for half in ("Upper", "Lower"):
            mid_ctrl = mid_controls.get(half)
            if not mid_ctrl:
                continue

            for side in self.sides:
                corner_ctrl = corner_controls.get(side)
                if not corner_ctrl:
                    continue

                for key in ("01", "02"):
                    self._build_chain_link(half, side, key,
                                           mid_ctrl, corner_ctrl)

        # 4. Recoger todo lo que quedo suelto en el mundo.
        roots = []
        for control in self.controls.values():
            node = control
            while True:
                parent = cmds.listRelatives(node, parent=True, type="transform")
                if not parent:
                    break
                node = parent[0]
            if node not in roots:
                roots.append(node)

        if roots:
            self.module_group = cmds.group(roots, n=group_name)

        # Si el jaw ya existe, se engancha ahora. Si no, lo hara build_module
        # cuando construya la mandibula.
        if not self.attach_to_jaw():
            cmds.warning("[SimpleMouth] Todavia no hay controles de jaw. "
                         "La boca queda montada pero sin seguir a la mandibula "
                         "hasta que se llame a attach_to_jaw().")

        print(f"[SimpleMouth] {len(self.controls)} controles y joints.")

        return self.module_group