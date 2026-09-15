import math

import maya.cmds as cmds


class FingersExtraModule(object):
    """Atributos extra de la mano (fan, spread, fist) resueltos con set driven keys.

    Se cuelgan del mismo control donde viven los switches IK/FK de los dedos
    ({prefix}_fingersSettings_CTRL), debajo de un separador EXTRA ATTR.

        fan     -> rotateZ del primer control de cada dedo, en gradiente (abanico)
        spread  -> rotateY del primer control de cada dedo, en gradiente (separar)
        fist    -> cierra el puño entero, todos los controles de todos los dedos

    fan y spread se saltan el metacarpo y excluyen al pulgar. fist sí incluye al
    pulgar, con su propio eje de curvatura y su propia escala.

    Los SDK NO se hacen sobre el control, se hacen sobre su grupo _SDK, para que
    el animador siga teniendo los controles libres para animar encima.

    Uso:
        extra = FingersExtraModule(rig_name="Arm", side="L")
        extra.build()

        # o reaprovechando la instancia del módulo de dedos:
        extra = FingersExtraModule(rig_name="Arm", side="L", fingers_module=fingers)
        extra.build()
    """

    # Orden anatómico conocido, para saber quién va primero en el abanico
    DEFAULT_ORDER = ["thumb", "pulgar", "index", "indice", "middle", "medio",
                     "ring", "anular", "pinky", "little", "menique", "minimo"]

    # ------------------------------------------------------------------ #
    #  INIT
    # ------------------------------------------------------------------ #
    def __init__(self, rig_name="Character", side="L",
                 settings_ctrl=None,
                 fingers_module=None):

        self.rig_name = rig_name
        self.side     = side
        self.prefix   = f"{self.side}_{self.rig_name}"

        self.settings_ctrl  = settings_ctrl
        self.fingers_module = fingers_module

        # --- atributos ---
        self.separator_name = "EXTRA_ATTR"
        self.separator_nice = "EXTRA ATTR"
        self.attr_min = -10.0
        self.attr_max = 10.0

        # --- grados que se alcanzan con el atributo a 10 ---
        self.fan_angle    = 15.0
        self.spread_angle = 12.0
        self.fist_angle   = 80.0

        # --- ejes ---
        self.fan_axis    = "rotateZ"
        self.spread_axis = "rotateY"

        # Eje de curvatura para el fist. None = detectarlo por geometría (recomendado,
        # es lo que hace que el pulgar cierre bien). Si lo fuerzas: "z", "-z", "y"...
        self.curl_axis = None
        self.curl_axis_override = {}      # {"thumb": "-z"}

        # Cuánto cierra cada falange respecto a fist_angle (proximal, media, distal...)
        self.fist_profile = [0.7, 1.0, 0.9]
        self.thumb_fist_scale = 0.6       # el pulgar cierra menos
        self.fist_include_metacarpal = False

        # Índice del primer control "real" de cada dedo. None = automático
        # (1 si el dedo tiene metacarpo, 0 si no).
        self.base_index = None

        # Orden de los dedos. None = se deduce del nombre.
        self.finger_order = None

        # Invertir el sentido del abanico si sale al revés
        self.fan_invert = False
        self.spread_invert = False

        # Relleno en el build
        self.fingers = {}                 # {finger_name: [ctrls en orden]}
        self.driven = []                  # [(nodo, atributo), ...]

    # ------------------------------------------------------------------ #
    #  MATEMÁTICAS (para detectar el eje de curvatura, igual que en fingers_module)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sub(a, b):
        return [a[i] - b[i] for i in range(3)]

    @staticmethod
    def _dot(a, b):
        return sum(a[i] * b[i] for i in range(3))

    @staticmethod
    def _cross(a, b):
        return [a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0]]

    @staticmethod
    def _mag(a):
        return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])

    @classmethod
    def _norm(cls, a):
        m = cls._mag(a)
        if m < 1e-9:
            return [0.0, 0.0, 0.0]
        return [a[0] / m, a[1] / m, a[2] / m]

    @classmethod
    def _local_axes(cls, node):
        m = cmds.getAttr(f"{node}.worldMatrix[0]")
        return [cls._norm([m[0], m[1], m[2]]),
                cls._norm([m[4], m[5], m[6]]),
                cls._norm([m[8], m[9], m[10]])]

    @staticmethod
    def _parse_axis(token):
        """'-z' -> ('rotateZ', -1.0)"""
        token = str(token).strip().lower()
        sign = -1.0 if token.startswith("-") else 1.0
        letter = token.lstrip("+-")
        attr = {"x": "rotateX", "y": "rotateY", "z": "rotateZ"}.get(letter, "rotateZ")
        return attr, sign

    # ------------------------------------------------------------------ #
    #  LOCALIZAR CONTROLES
    # ------------------------------------------------------------------ #
    def get_settings_ctrl(self):
        """El control donde se cuelgan los atributos."""
        if self.settings_ctrl and cmds.objExists(self.settings_ctrl):
            return self.settings_ctrl

        if self.fingers_module and getattr(self.fingers_module, "settings_ctrl", None):
            if cmds.objExists(self.fingers_module.settings_ctrl):
                self.settings_ctrl = self.fingers_module.settings_ctrl
                return self.settings_ctrl

        guess = f"{self.prefix}_fingersSettings_CTRL"
        if cmds.objExists(guess):
            self.settings_ctrl = guess
            return guess

        cmds.warning(f"[fingersExtra] No encuentro el control de ajustes "
                     f"({guess}). Pásamelo con settings_ctrl=...")
        return None

    def get_fingers(self):
        """{nombre_dedo: [controles FK en orden de la cadena]}."""
        fingers = {}

        # 1. Si tenemos la instancia del módulo de dedos, de ahí sale todo
        if self.fingers_module and getattr(self.fingers_module, "fingers_data", None):
            for name, data in self.fingers_module.fingers_data.items():
                ctrls = [c for c in (data.get("fk_ctrls") or []) if cmds.objExists(c)]
                if ctrls:
                    fingers[name] = ctrls
            if fingers:
                return fingers

        # 2. Si no, rastreamos la escena por los grupos que crea el módulo de dedos
        grps = cmds.ls(f"{self.prefix}_*_fkCtrls_GRP", type="transform", long=True) or []
        for grp in grps:
            short = grp.split("|")[-1]
            name = short.replace(f"{self.prefix}_", "").replace("_fkCtrls_GRP", "")

            kids = cmds.listRelatives(grp, ad=True, type="transform", f=True) or []
            ctrls = [c for c in kids if c.endswith("_fk_CTRL")]
            # Los controles van anidados unos dentro de otros, así que la
            # profundidad de la ruta da el orden de la cadena
            ctrls.sort(key=lambda p: p.count("|"))
            if ctrls:
                fingers[name] = ctrls

        return fingers

    def sort_fingers(self, names):
        """Ordena los dedos de pulgar a meñique."""
        if self.finger_order:
            order = list(self.finger_order)
        else:
            order = self.DEFAULT_ORDER

        def key(name):
            low = name.lower()
            for i, token in enumerate(order):
                if token in low:
                    return (0, i, name)
            return (1, 0, name)      # los que no reconozco, al final

        return sorted(names, key=key)

    def is_thumb(self, name):
        low = name.lower()
        return "thumb" in low or "pulgar" in low

    def get_base_index(self, ctrls):
        """Primer control 'real' del dedo, saltándose el metacarpo."""
        if self.base_index is not None:
            return min(self.base_index, len(ctrls) - 1)
        # 4 controles o más = hay metacarpo, así que empezamos en el segundo
        return 1 if len(ctrls) >= 4 else 0

    @staticmethod
    def get_sdk_node(ctrl):
        """Devuelve el grupo _SDK del control (o el mejor sustituto disponible)."""
        short = ctrl.split("|")[-1]
        for suffix in ("_SDK", "_OFF", "_SPC", "_GRP"):
            candidate = short.replace("_CTRL", suffix)
            if cmds.objExists(candidate):
                return candidate

        parent = cmds.listRelatives(ctrl, p=True, f=True)
        if parent:
            cmds.warning(f"[fingersExtra] No encuentro grupo _SDK para {short}, "
                         f"uso su padre directo.")
            return parent[0]

        cmds.warning(f"[fingersExtra] {short} no tiene grupo encima. Hago el SDK "
                     f"sobre el propio control (perderás la animación manual ahí).")
        return ctrl

    # ------------------------------------------------------------------ #
    #  EJE DE CURVATURA PARA EL FIST
    # ------------------------------------------------------------------ #
    def detect_curl_normal(self, nodes):
        """Normal del plano en el que ya está doblada la cadena de controles."""
        pts = [cmds.xform(n, q=True, ws=True, t=True) for n in nodes]
        best_n, best_mag = None, 0.0
        for i in range(len(pts) - 2):
            v1 = self._norm(self._sub(pts[i + 1], pts[i]))
            v2 = self._norm(self._sub(pts[i + 2], pts[i + 1]))
            n = self._cross(v1, v2)
            m = self._mag(n)
            if m > best_mag:
                best_mag, best_n = m, n
        if best_n is not None and best_mag > 1e-3:
            return self._norm(best_n)
        return None

    def get_curl_axes(self, finger_name, ctrls):
        """[(atributo, signo), ...] para cada control del dedo."""
        # 1. Override explícito
        if finger_name in self.curl_axis_override:
            attr, sign = self._parse_axis(self.curl_axis_override[finger_name])
            return [(attr, sign)] * len(ctrls)

        # 2. Eje fijo para toda la mano
        if self.curl_axis:
            attr, sign = self._parse_axis(self.curl_axis)
            return [(attr, sign)] * len(ctrls)

        # 3. Detección por geometría (es lo que hace que el pulgar cierre bien)
        chain = list(ctrls)
        last_jnt = ctrls[-1].split("|")[-1].replace("_CTRL", "_JNT")
        if cmds.objExists(last_jnt):
            tip = cmds.listRelatives(last_jnt, c=True, type="joint") or []
            if tip:
                chain = chain + [tip[0]]

        normal = self.detect_curl_normal(chain) if len(chain) >= 3 else None
        if normal is None:
            cmds.warning(f"[fingersExtra] '{finger_name}' está recto: uso rotateZ para "
                         f"el fist. Si cierra al revés, usa curl_axis_override.")
            return [("rotateZ", 1.0)] * len(ctrls)

        out = []
        attrs = ("rotateX", "rotateY", "rotateZ")
        for ctrl in ctrls:
            axes = self._local_axes(ctrl)
            dots = [self._dot(normal, a) for a in axes]
            idx = max(range(3), key=lambda i: abs(dots[i]))
            out.append((attrs[idx], 1.0 if dots[idx] > 0 else -1.0))
        return out

    # ------------------------------------------------------------------ #
    #  SET DRIVEN KEYS
    # ------------------------------------------------------------------ #
    def set_driven(self, node, attr, driver, value_at_max):
        """Tres claves: -10 / 0 / +10, con tangentes lineales."""
        plug = f"{node}.{attr}"
        if not cmds.objExists(plug):
            cmds.warning(f"[fingersExtra] No existe {plug}, me lo salto.")
            return
        if cmds.getAttr(plug, lock=True):
            cmds.warning(f"[fingersExtra] {plug} está bloqueado, me lo salto.")
            return

        for driver_value, value in ((self.attr_min, -value_at_max),
                                    (0.0, 0.0),
                                    (self.attr_max, value_at_max)):
            cmds.setDrivenKeyframe(plug,
                                   cd=driver,
                                   dv=driver_value,
                                   v=value,
                                   itt="linear",
                                   ott="linear")

        if (node, attr) not in self.driven:
            self.driven.append((node, attr))

    # ------------------------------------------------------------------ #
    #  LIMPIEZA
    # ------------------------------------------------------------------ #
    def delete_previous(self, remove_attrs=False):
        """Borra los SDK de un build anterior para poder relanzar sin duplicar claves."""
        ctrl = self.get_settings_ctrl()
        fingers = self.get_fingers()

        junk = []
        for name, ctrls in fingers.items():
            for c in ctrls:
                sdk = self.get_sdk_node(c)
                for axis in ("rotateX", "rotateY", "rotateZ"):
                    plug = f"{sdk}.{axis}"
                    if not cmds.objExists(plug):
                        continue
                    inputs = cmds.listConnections(plug, s=True, d=False) or []
                    for node in inputs:
                        node_type = cmds.nodeType(node)
                        if node_type.startswith("animCurveU") or node_type == "blendWeighted":
                            junk.append(node)
                            # las curvas que entran en el blendWeighted también
                            for up in (cmds.listConnections(node, s=True, d=False) or []):
                                if cmds.nodeType(up).startswith("animCurveU"):
                                    junk.append(up)

        junk = list({j for j in junk if cmds.objExists(j)})
        if junk:
            cmds.delete(junk)

        if remove_attrs and ctrl:
            for attr in ("fan", "spread", "fist", self.separator_name):
                plug = f"{ctrl}.{attr}"
                if cmds.objExists(plug):
                    cmds.setAttr(plug, lock=False)
                    cmds.deleteAttr(plug)

        print(f"[fingersExtra] Limpieza: {len(junk)} nodos de SDK borrados.")

    # ------------------------------------------------------------------ #
    #  ATRIBUTOS
    # ------------------------------------------------------------------ #
    def create_attributes(self, ctrl):
        """Separador EXTRA ATTR + fan / spread / fist."""
        if not cmds.attributeQuery(self.separator_name, node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln=self.separator_name, nn=self.separator_nice,
                         at="enum", en="------", k=True)
            try:
                cmds.setAttr(f"{ctrl}.{self.separator_name}", cb=True)
                cmds.setAttr(f"{ctrl}.{self.separator_name}", lock=True)
            except Exception:
                pass

        for attr in ("fan", "spread", "fist"):
            if not cmds.attributeQuery(attr, node=ctrl, exists=True):
                cmds.addAttr(ctrl, ln=attr, at="double",
                             min=self.attr_min, max=self.attr_max, dv=0.0, k=True)

    # ------------------------------------------------------------------ #
    #  BUILD
    # ------------------------------------------------------------------ #
    def build(self):
        ctrl = self.get_settings_ctrl()
        if not ctrl:
            return

        self.fingers = self.get_fingers()
        if not self.fingers:
            cmds.warning(f"[fingersExtra] No encuentro controles de dedos para {self.prefix}.")
            return

        self.create_attributes(ctrl)

        names = self.sort_fingers(list(self.fingers.keys()))
        no_thumb = [n for n in names if not self.is_thumb(n)]

        print(f"\n[fingersExtra] {self.prefix} -> orden: {names}")
        if not no_thumb:
            cmds.warning("[fingersExtra] Todos los dedos me parecen pulgares. "
                         "Revisa los nombres o usa finger_order.")

        # ---------------- FAN y SPREAD ---------------- #
        # Gradiente de -1 a +1 a lo largo de la mano: el índice tira para un lado,
        # el meñique para el otro y el corazón casi no se mueve. Sin gradiente los
        # dedos girarían todos igual y no se abrirían.
        total = len(no_thumb)
        for i, name in enumerate(no_thumb):
            ctrls = self.fingers[name]
            base = self.get_base_index(ctrls)
            sdk = self.get_sdk_node(ctrls[base])

            mult = -1.0 + (2.0 * i / float(total - 1)) if total > 1 else 0.0

            fan_mult = -mult if self.fan_invert else mult
            spread_mult = -mult if self.spread_invert else mult

            self.set_driven(sdk, self.fan_axis, f"{ctrl}.fan",
                            self.fan_angle * fan_mult)
            self.set_driven(sdk, self.spread_axis, f"{ctrl}.spread",
                            self.spread_angle * spread_mult)

        # ---------------- FIST ---------------- #
        for name in names:
            ctrls = self.fingers[name]
            base = 0 if self.fist_include_metacarpal else self.get_base_index(ctrls)
            targets = ctrls[base:]
            if not targets:
                continue

            axes = self.get_curl_axes(name, targets)
            scale = self.thumb_fist_scale if self.is_thumb(name) else 1.0

            for depth, (c, (attr, sign)) in enumerate(zip(targets, axes)):
                profile = self.fist_profile[min(depth, len(self.fist_profile) - 1)]
                angle = self.fist_angle * profile * scale * sign
                self.set_driven(self.get_sdk_node(c), attr, f"{ctrl}.fist", angle)

        print(f"[fingersExtra] Listo: {len(self.driven)} canales conducidos desde {ctrl}.\n")

    # ------------------------------------------------------------------ #
    #  DEBUG
    # ------------------------------------------------------------------ #
    def debug(self):
        """Imprime qué dedos ve, en qué orden y con qué eje de cierre."""
        self.fingers = self.get_fingers()
        names = self.sort_fingers(list(self.fingers.keys()))

        print(f"\n--- FINGERS EXTRA  {self.prefix} ---")
        print(f"  control de ajustes: {self.get_settings_ctrl()}")
        for name in names:
            ctrls = self.fingers[name]
            base = self.get_base_index(ctrls)
            axes = self.get_curl_axes(name, ctrls[base:])
            tag = " (pulgar, fuera de fan/spread)" if self.is_thumb(name) else ""
            axes_txt = ", ".join(f"{a[-1]}{'+' if s > 0 else '-'}" for a, s in axes)
            print(f"  {name:<10} {len(ctrls)} ctrls, base={base}{tag}")
            print(f"{'':<13}fan/spread -> {ctrls[base].split('|')[-1]}")
            print(f"{'':<13}fist       -> {axes_txt}")
        print("--- fin ---\n")