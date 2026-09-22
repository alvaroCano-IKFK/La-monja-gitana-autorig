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

        mid           parentConstraint 100% al control del jaw de su mitad
        in01          parentConstraint  mid 75% / comisura 25%
        in02          parentConstraint  mid 25% / comisura 75%
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

        # ==========================================================
        # CASCADA
        # ----------------------------------------------------------
        # Una curva por labio, con un CV por control:
        #   comisuraR - pinchR - levatorR - mid - levatorL - pinchL - comisuraL
        # Cada control mueve SU CV, y los eslabones intermedios (levator,
        # depresor, pinch) siguen a la curva en posicion. Como la curva es de
        # grado 3, el punto de cada eslabon depende de los CVs vecinos: mover
        # un control empuja un poco a los de al lado.
        #
        # La ROTACION no cambia: sigue saliendo del parentConstraint entre el
        # mid y la comisura, que es lo que evita los flips. La curva solo
        # aporta DONDE, nunca COMO.
        #
        # use_cascade = False  -> exactamente el sistema anterior, solo
        #                         constraints.
        # cascade_amount       -> 0 = posicion solo de los constraints,
        #                         1 = posicion solo de la curva.
        # ==========================================================
        self.use_cascade = True
        self.cascade_amount = 1.0
        self.cascade_links = {}
        self.cascade_group = None

        # control -> nodo por el que se lee desde fuera (el propio control en
        # L, su _out_TRN en R). Ver _insert_mirror.
        self.output_nodes = {}


    # ------------------------------------------------------------------
    # UTILIDADES
    # ------------------------------------------------------------------
    def _guide_transform(self, guide, side):
        """
        Posicion y orientacion mundiales de una guia. Para el lado R, el
        espejo se construye a mano, eje por eje.

        POR QUE A MANO
        --------------
        Un espejo puro en X da un marco de ejes zurdo, y un zurdo no se puede
        escribir con una rotacion: una rotacion siempre deja el marco diestro.
        La version anterior metia la matriz bajo un grupo con scaleX = -1 y le
        preguntaba a Maya la rotacion en mundo. Maya tiene que partir esa
        matriz en rotacion + escala negativa, y decide el solo en que eje pone
        el -1. La rotacion que salia no era un espejo de nada: por eso los
        controles R no se movian en espejo.

        LO QUE SE HACE AHORA
        --------------------
        Con m(v) = (-vx, vy, vz) el reflejo de un vector en el plano YZ, el
        grupo del control R se orienta con

            x_R = -m(x_L)      y_R = m(y_L)      z_R = m(z_L)

        que SI es diestro (reflejar invierte la mano, negar un eje la vuelve a
        invertir), o sea una rotacion normal que Maya escribe sin trampas. El
        eje X que falta por reflejar lo pone el grupo _mirror_GRP con
        scaleX = -1 que _make_control mete debajo del grupo raiz. Resultado: el
        control R es el reflejo exacto del L, y los mismos valores en los dos
        lados dan movimientos en espejo en los tres ejes.

        Devuelve (posicion, rotacion) o (None, None).
        """
        if not cmds.objExists(guide):
            cmds.warning(f"[SimpleMouth] No existe la guia '{guide}'.")
            return None, None

        position = cmds.xform(guide, q=True, ws=True, t=True)
        rotation = cmds.xform(guide, q=True, ws=True, ro=True)

        if side != "R":
            return position, rotation

        m = cmds.xform(guide, q=True, ws=True, matrix=True)
        x_axis, y_axis, z_axis = m[0:3], m[4:7], m[8:11]

        x_r = [x_axis[0], -x_axis[1], -x_axis[2]]     # -m(x)
        y_r = [-y_axis[0], y_axis[1], y_axis[2]]      #  m(y)
        z_r = [-z_axis[0], z_axis[1], z_axis[2]]      #  m(z)
        t_r = [-position[0], position[1], position[2]]

        mirrored = (x_r + [0.0] + y_r + [0.0] + z_r + [0.0] + t_r + [1.0])

        # Un transform temporal SIN escalas negativas: la matriz ya es una
        # rotacion propia, asi que Maya la descompone sin ambiguedad.
        temp = cmds.group(em=True, n="tempMirrorTRN")
        cmds.xform(temp, ws=True, matrix=mirrored)
        position = cmds.xform(temp, q=True, ws=True, t=True)
        rotation = cmds.xform(temp, q=True, ws=True, ro=True)
        cmds.delete(temp)

        return position, rotation

    def _make_control(self, name, position, rotation=None, normal=(0, 0, 1),
                      mirrored=False):
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

        self.output_nodes[control] = control

        if mirrored:
            self._insert_mirror(control, group)

        return control, group

    def _insert_mirror(self, control, group):
        """
        Mete el reflejo en X dentro de la jerarquia del control R.

            GRP              <- constraints (marco diestro, sin tocar)
              _mirror_GRP    <- scaleX = -1   (NUEVO)
                SPC > OFF > SDK > ANIM > CTRL
                                          _out_TRN  <- scaleX = -1 (NUEVO)

        El reflejo va DEBAJO del GRP y no encima: un parentConstraint no sabe
        escribir un reflejo, asi que si el nodo constreñido estuviera dentro de
        un espacio negativo, el constraint devolveria orientaciones raras.
        Asi el GRP sigue siendo un transform normal y los constraints trabajan
        como siempre.

        El _out_TRN deshace el reflejo para todo lo que tenga que LEER este
        control desde fuera: el joint (un joint con escala negativa invierte
        las normales del skin) y los constraints de otros controles que usan
        este como padre. Nadie fuera del control ve nunca la escala -1.
        """
        base = control[:-len("_CTRL")] if control.endswith("_CTRL") else control
        spc = f"{base}_SPC"

        if not cmds.objExists(spc):
            cmds.warning(f"[SimpleMouth] No encuentro '{spc}', "
                         f"'{control}' se queda sin espejo.")
            return None

        mirror = cmds.group(em=True, n=f"{base}_mirror_GRP", parent=group)
        cmds.setAttr(f"{mirror}.scaleX", -1)

        # relative=True: el SPC conserva sus valores locales (identidad). Sin
        # esto, cmds.parent compensaria la escala del nuevo padre y el reflejo
        # se anularia en el propio SPC.
        cmds.parent(spc, mirror, relative=True)

        out = cmds.group(em=True, n=f"{base}_out_TRN", parent=control)
        cmds.setAttr(f"{out}.scaleX", -1)
        self.output_nodes[control] = out

        return mirror

    def _out(self, control):
        """
        Nodo que hay que usar para LEER un control desde fuera.

        En el lado L es el propio control. En el R es su _out_TRN, que tiene la
        misma posicion y un marco diestro. Ningun joint ni constraint debe
        apuntar al control R directamente.
        """
        return self.output_nodes.get(control, control)

    def _make_joint(self, name, control):
        """
        Joint en la posicion del control y constreñido a el.

        parentConstraint y scaleConstraint: el joint es un pasajero del control
        y no tiene vida propia.
        """
        if cmds.objExists(name):
            cmds.delete(name)

        driver = self._out(control)

        cmds.select(clear=True)
        joint = cmds.joint(n=name)
        cmds.matchTransform(joint, driver, pos=True, rot=True)

        cmds.parentConstraint(driver, joint, mo=False)
        cmds.scaleConstraint(driver, joint, mo=False)

        cmds.select(clear=True)

        return joint

    def _blend_constraint(self, driver_a, driver_b, target, weight_a,
                          skip_translate=False):
        """
        parentConstraint de dos targets con pesos, en Shortest.

        interpType 2 (Shortest) no es opcional: el valor por defecto (Average)
        promedia angulos de Euler, y promediar 179 con -179 da 0 en vez de 180.
        Ahi es donde salen los saltos.
        """
        kwargs = {"mo": True}
        if skip_translate:
            kwargs["skipTranslate"] = ["x", "y", "z"]

        constraint = cmds.parentConstraint(driver_a, driver_b, target, **kwargs)[0]

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
        El control del centro de un labio.

        Un solo control: lo conduce el jaw al 100% (el constraint se pone en
        attach_to_jaw, sobre su grupo raiz) y el animador anima el propio
        control, porque el constraint escribe en el grupo y no en los canales
        del control. No se pisan.
        """
        position, rotation = self._guide_transform(self.lip_mid, "L")
        if position is None:
            return None, None

        name = f"C_{self.rig_name}_lip{half}Mid_CTRL"
        control, group = self._make_control(name, position, rotation)

        self.mid_groups[half] = group
        self.controls[f"{half}Mid"] = control

        self._make_joint(f"C_{self.rig_name}_lip{half}Mid_JNT", control)

        return control, None

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
        control, group = self._make_control(name, position, rotation,
                                            mirrored=(side == "R"))

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

        control, group = self._make_control(name, position, rotation,
                                            mirrored=(side == "R"))

        # Los padres se leen por su nodo de salida: el de la comisura R tiene
        # escala negativa y no puede ser target de un constraint a pelo.
        mid_ctrl = self._out(mid_ctrl)
        corner_ctrl = self._out(corner_ctrl)

        weight = self.CHAIN_WEIGHTS[key]

        if self.use_cascade:
            # Rotacion: igual que siempre, del blend de los dos padres.
            # La traslacion la pone _build_cascade_curve mas tarde.
            self._blend_constraint(mid_ctrl, corner_ctrl, group, weight,
                                   skip_translate=True)

            # BASE: el mismo blend, completo, en un transform aparte. Es donde
            # estaria el grupo sin cascada. Hace dos cosas: sirve de target
            # para dosificar la cascada con cascade_amount, y es el espacio
            # donde se suma lo que mueve el animador para colocar el CV.
            prefix = f"{side}_{self.rig_name}_{base_name}"
            base = cmds.group(em=True, n=f"{prefix}CascadeBase_TRN",
                              parent=self._get_cascade_group())
            cmds.matchTransform(base, group, pos=True, rot=True)
            self._blend_constraint(mid_ctrl, corner_ctrl, base, weight)

            # LOCAL: hijo de la base que copia el translate del control. Su
            # mundo es "base + lo que ha movido el animador", que es donde
            # tiene que ir el CV de este control. Lee el canal translate, no
            # el worldMatrix del control, asi que no depende del grupo que la
            # curva va a mover: no hay ciclo.
            # En el lado R el control se mueve dentro de un espacio reflejado
            # (su _mirror_GRP). El Local tiene que moverse en el MISMO espacio,
            # o el CV iria hacia un lado en X y el control hacia el otro, y el
            # NEG ya no cancelaria. Por eso lleva su propio reflejo delante.
            local_parent = base
            if side == "R":
                local_parent = cmds.group(em=True, parent=base,
                                          n=f"{prefix}CascadeMirror_GRP")
                cmds.setAttr(f"{local_parent}.scaleX", -1)

            local = cmds.group(em=True, n=f"{prefix}CascadeLocal_TRN",
                               parent=local_parent)
            cmds.connectAttr(f"{control}.translate", f"{local}.translate")

            self.cascade_links[(half, side, key)] = {
                "control": control,
                "group": group,
                "spc": f"{prefix}_SPC",
                "base": base,
                "local": local,
            }
        else:
            self._blend_constraint(mid_ctrl, corner_ctrl, group, weight)

        print(f"[SimpleMouth] {group}: {mid_ctrl} {weight:.2f} / "
              f"{corner_ctrl} {1.0 - weight:.2f}")

        self.controls[f"{side}{base_name}"] = control
        self._make_joint(f"{side}_{self.rig_name}_{base_name}_JNT", control)

        return control

    def _get_cascade_group(self):
        """Grupo donde viven las bases, las curvas y los followers."""
        name = f"C_{self.rig_name}_mouthCascade_GRP"
        if not cmds.objExists(name):
            cmds.group(em=True, n=name)

            # inheritsTransform a 0: este grupo NO hereda nada de sus padres.
            #
            # Aqui dentro viven nodos que reciben posiciones en MUNDO por
            # conexion directa: las curvas (decomposeMatrix -> controlPoints) y
            # los followers (pointOnCurveInfo.position -> translate). Una
            # conexion directa no compensa al padre. Si este grupo acaba dentro
            # de algo que se mueve (el mouth_GRP bajo la cabeza, o el global
            # del personaje), esas posiciones se aplicarian DOS veces: la que
            # ya traen en mundo, mas la del padre. Al mover el personaje, toda
            # la cascada se iria el doble de lejos.
            #
            # Con inheritsTransform a 0 el grupo se queda siempre en el origen
            # del mundo, este donde este en la jerarquia, y espacio de objeto
            # = mundo se cumple siempre.
            cmds.setAttr(f"{name}.inheritsTransform", 0)

        self.cascade_group = name
        return name

    @staticmethod
    def _nearest_parameter(curve, position):
        """Parametro del punto de la curva mas cercano a una posicion."""
        shape = cmds.listRelatives(curve, shapes=True)[0]
        node = cmds.createNode("nearestPointOnCurve")
        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{node}.inputCurve")
        cmds.setAttr(f"{node}.inPosition", *position)
        parameter = cmds.getAttr(f"{node}.parameter")
        cmds.delete(node)
        return parameter

    @staticmethod
    def _cv_influence(curve, index, parameter):
        """
        Cuanto se mueve el punto de la curva en 'parameter' si el CV 'index'
        se mueve una unidad.

        En una curva no racional, punto(u) = suma de N_j(u) * CV_j, asi que la
        respuesta es exactamente N_index(u): un numero fijo entre 0 y 1, el
        mismo para X, Y y Z. Se mide empujando el CV y mirando cuanto se mueve
        el punto, que es mas facil que evaluar la base a mano.
        """
        before = cmds.pointOnCurve(curve, pr=parameter, p=True)
        cmds.move(1, 0, 0, f"{curve}.cv[{index}]", r=True, ws=True)
        after = cmds.pointOnCurve(curve, pr=parameter, p=True)
        cmds.move(-1, 0, 0, f"{curve}.cv[{index}]", r=True, ws=True)
        return after[0] - before[0]

    def _build_cascade_curve(self, half, mid_ctrl, corner_controls):
        """
        La curva de un labio y todo lo que cuelga de ella.

        EL PROBLEMA DEL DOBLE MOVIMIENTO
        --------------------------------
        Si un eslabon sigue a una curva y ademas mueve un CV de esa misma
        curva, se mueve dos veces: el animador lo desplaza 1, su CV se desplaza
        1, la curva en su punto se desplaza k (su propia influencia, entre 0 y
        1), su grupo le sigue, y el control acaba en 1 + k. Por eso el sistema
        viejo tenia una curva distinta para cada control: cada uno iba sobre
        una curva que no conducia el mismo. Y por eso tenia PreBind.

        LA SALIDA: UN NEG
        -----------------
        Con una sola curva se compensa restando. Como k es un numero fijo
        (N_i(u_i), ver _cv_influence), el grupo se mueve exactamente
        k * cascade_amount * lo que mueve el animador. Asi que el SPC del
        control, que esta libre, recibe menos esa cantidad con un
        multiplyDivide. Es el truco del NEG de la infografia de RIVETS.

        El animador mueve 1 -> el control se mueve 1. Los vecinos, lo que les
        toque segun la curva. Eso es la cascada sin doble transformacion.
        """
        order = [("R", "corner"), ("R", "02"), ("R", "01"),
                 (None, "mid"),
                 ("L", "01"), ("L", "02"), ("L", "corner")]

        drivers = []
        for side, key in order:
            if key == "mid":
                drivers.append(mid_ctrl)
            elif key == "corner":
                drivers.append(corner_controls.get(side))
            else:
                link = self.cascade_links.get((half, side, key))
                drivers.append(link["local"] if link else None)

        if not all(drivers):
            cmds.warning(f"[SimpleMouth] Cascada {half}: hacen falta los dos "
                         f"lados completos. Se queda solo con constraints.")
            return None

        positions = [cmds.xform(d, q=True, ws=True, t=True) for d in drivers]

        curve_name = f"C_{self.rig_name}_lip{half}Cascade_CRV"
        if cmds.objExists(curve_name):
            cmds.delete(curve_name)
        curve = cmds.curve(d=3, p=positions, n=curve_name)
        cmds.parent(curve, self._get_cascade_group())
        shape = cmds.listRelatives(curve, shapes=True)[0]

        # 1. Parametro e influencia propia de cada eslabon. Tiene que ir ANTES
        #    de conectar los CVs, porque _cv_influence los empuja a mano.
        for index, (side, key) in enumerate(order):
            if key in ("mid", "corner"):
                continue
            link = self.cascade_links[(half, side, key)]
            link["parameter"] = self._nearest_parameter(curve, positions[index])
            link["k"] = self._cv_influence(curve, index, link["parameter"])

        # 2. Cada CV sigue a su control. El grupo de la curva esta en el
        #    origen, asi que espacio de objeto = mundo.
        for index, driver in enumerate(drivers):
            decompose = cmds.createNode(
                "decomposeMatrix", n=f"{curve}_cv{index:02d}_DCM")
            cmds.connectAttr(f"{driver}.worldMatrix[0]",
                             f"{decompose}.inputMatrix")
            cmds.connectAttr(f"{decompose}.outputTranslate",
                             f"{shape}.controlPoints[{index}]")

        # 3. Cada eslabon sigue a la curva, y su NEG le quita su propio empuje.
        for (h, side, key), link in self.cascade_links.items():
            if h != half:
                continue

            prefix = link["base"].replace("CascadeBase_TRN", "")

            info = cmds.createNode("pointOnCurveInfo",
                                   n=f"{prefix}Cascade_POCI")
            cmds.connectAttr(f"{shape}.worldSpace[0]", f"{info}.inputCurve")
            cmds.setAttr(f"{info}.parameter", link["parameter"])

            follower = cmds.group(em=True, n=f"{prefix}CascadeFollow_TRN",
                                  parent=self._get_cascade_group())
            cmds.connectAttr(f"{info}.position", f"{follower}.translate")

            # Posicion del grupo: mezcla entre sin cascada (base) y con
            # cascada (curva). mo=True absorbe que la curva de grado 3 no pasa
            # exactamente por los CVs de dentro.
            point = cmds.pointConstraint(link["base"], follower, link["group"],
                                         mo=True)[0]
            aliases = cmds.pointConstraint(point, q=True, weightAliasList=True)
            cmds.setAttr(f"{point}.{aliases[0]}", 1.0 - self.cascade_amount)
            cmds.setAttr(f"{point}.{aliases[1]}", self.cascade_amount)

            # NEG: el SPC resta lo que la curva ha empujado al grupo por culpa
            # del propio control.
            compensation = link["k"] * self.cascade_amount
            if cmds.objExists(link["spc"]) and compensation:
                neg = cmds.createNode("multiplyDivide", n=f"{prefix}Cascade_NEG")
                cmds.connectAttr(f"{link['control']}.translate", f"{neg}.input1")
                cmds.setAttr(f"{neg}.input2", -compensation, -compensation,
                             -compensation, type="double3")
                cmds.connectAttr(f"{neg}.output", f"{link['spc']}.translate")

            print(f"[SimpleMouth] {link['group']}: sigue a {curve} en "
                  f"u={link['parameter']:.3f}, influencia propia "
                  f"k={link['k']:.3f} (compensada)")

        return curve

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

        # 1. Cada centro de labio, al 100% a su mitad de la mandibula.
        for half, group in self.mid_groups.items():
            if not group or not cmds.objExists(group):
                continue
            jaw_ctrl = (self.jaw_upper_ctrl if half == "Upper"
                        else self.jaw_lower_ctrl)
            cmds.parentConstraint(jaw_ctrl, group, mo=True)
            print(f"[SimpleMouth] {group} <- {jaw_ctrl} (100%)")

        # 2. Las comisuras, entre las dos mitades, con su atributo animable.
        for side, group in self.corner_groups.items():
            if not group or not cmds.objExists(group):
                continue

            control = self.controls.get(f"{side}Corner")
            constraint = self._blend_constraint(
                self.jaw_upper_ctrl, self.jaw_lower_ctrl, group,
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
            print(f"[SimpleMouth] {group} <- {self.jaw_upper_ctrl} "
                  f"{weight:.2f} / {self.jaw_lower_ctrl} "
                  f"{self.corner_upper_lower:.2f}")

        self.attached_to_jaw = True

        return True

    def build(self):
        group_name = f"C_{self.rig_name}_mouth_GRP"
        if cmds.objExists(group_name):
            cmds.delete(group_name)

        self.controls = {}
        self.joints = {}
        self.cascade_links = {}
        self.output_nodes = {}

        cascade_name = f"C_{self.rig_name}_mouthCascade_GRP"
        if cmds.objExists(cascade_name):
            cmds.delete(cascade_name)
        self.cascade_group = None

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

        # 3b. La cascada: una curva por labio. Va despues de los eslabones
        #     porque necesita sus bases ya creadas.
        if self.use_cascade:
            for half in ("Upper", "Lower"):
                if mid_controls.get(half):
                    self._build_cascade_curve(half, mid_controls[half],
                                              corner_controls)

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

        if self.cascade_group and cmds.objExists(self.cascade_group):
            roots.append(self.cascade_group)

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