import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import spine_module
import limbs_module
import fingers_module
import extraFingerAttributes_module
import toes_module
import neck_module
import chest_module
import hip_module
import leg_module
import foot_module
import groups_module
import rigRoot_module
import mirror_module
import skinning_module
import guides_module
import body_module
import spaceSwitching_module
import headSpace_module
import curvature_module
import soft_module
import pvPin_module
import mouthModule
import jaw_module
import eyebrowsModule
import eyes_module
import nose_module
import horse_spine
import horse_neck
import horse_leg_module
import horse_tail

# El hip del caballo es un modulo aparte: el del biped no crea el body, lo lee
# de root_instance.body_ctl, que publica body_module en el paso _core_body. Ese
# paso no se ejecuta en cuadrupedo, asi que el del biped alli peta.
#
# El import va protegido para que el biped siga funcionando aunque el archivo
# del caballo no este en la carpeta.
try:
    import horse_hip_module
except ImportError:
    horse_hip_module = None
import socket_module
import progress_module
import controlsLibrary
import module_specs


class BuildRig(object):
    """
    Orquestador del rig.

    Ya no tiene la lista de modulos escrita a mano: recibe una RECETA desde la
    UI y construye exactamente lo que pone en ella.

        recipe = [
            {"type": "spine", "side": "C", "features": {...}},
            {"type": "arm",   "side": "L", "features": {"curvature", "twist"}},
            {"type": "arm",   "side": "R", "features": {"curvature", "twist", "soft_ik"}},
        ]

    Si el soft IK no esta en el set de features del brazo derecho, no se
    construye el soft del brazo derecho, y punto. El resto del brazo sale igual.
    """

    # Nombre del rig. Antes estaba repetido como "Character" en quince sitios.
    RIG_NAME = "Character"

    # ------------------------------------------------------------------
    # PASOS FIJOS DEL RIG
    #
    # Hay cosas que no son modulos elegibles: la raiz, el body, el skinning...
    # Se mezclan con los modulos de la receta por el numero de orden, que es el
    # mismo que usa module_specs (spine=10, arm=20, finger=30, leg=40).
    # ------------------------------------------------------------------
    #: (orden, metodo, etiqueta, plantillas). Sin plantillas = en todas.
    #:
    #: El chest es solo del biped: chest_module hace un aimConstraint contra
    #: {rig}_spine_3_JNT, que es un nombre de spine_module. HorseSpine llama a
    #: los suyos spine01_JNT, spine_pelvis_JNT y spine_chest_JNT.
    CORE_STEPS = [
        (0,  "_core_root",      "Root rig",      None),
        (1,  "_core_body",      "Body",          ("biped",)),
        (11, "_core_chest",     "Chest",         ("biped",)),
        # El hip va en las DOS plantillas: es quien monta el body (el COG con
        # pivote movible) y el localHip_CTL. Lo unico que cambia es de que
        # guia sale, porque el caballo no tiene "root".
        (13, "_core_hip",       "Hip",           None),
        (70, "_core_skinning",  "Skinning",      None),
        (80, "_core_post",      "Soft IK y pole vector pins", None),
        #(90, "_core_spaces",    "Space switching", None),
    ]

    # ------------------------------------------------------------------
    def __init__(self):
        self.modules = {}          # (tipo, lado) -> instancia construida
        self.recipe = []
        self.root_rig = None
        self.hip_rig = None
        self.template = module_specs.DEFAULT_TEMPLATE
        self.skip_core = set()

    # ------------------------------------------------------------------
    # ENTRADA
    # ------------------------------------------------------------------
    def build(self, recipe=None, show_progress=True, skip_core=None):
        """
        Metodo que llama el boton BUILD de la UI.

        Args:
            recipe (list): la receta que viene de Window.collect_recipe(). Si
                es None se construye el biped completo con las features por
                defecto, que es como se comportaba el autorig antes.
            show_progress (bool): False para tests o para lanzarlo en batch.
            skip_core (set): nombres de pasos fijos que NO se quieren construir.
                Util mientras se desarrolla: para probar solo un brazo,

                    BuildRig().build(recipe, skip_core={"_core_skinning"})

                La cara ya no esta aqui: son cuatro modulos de la receta, asi
                que para no construirla basta con no anadirlos al arbol.
        """
        self.skip_core = set(skip_core or ())
        if recipe is None:
            recipe = self.default_recipe()

        recipe, warnings = module_specs.normalize_recipe(recipe)

        # Guias R que falten (no se le dio a MIRROR, o las guias vienen de
        # GUIDES / un import). Solo rellena huecos: lo que ya existe no se toca.
        mirror_module.Mirror().mirror_missing(recipe)
        for text in warnings:
            cmds.warning("[Build] {}".format(text))

        if not recipe:
            cmds.warning("[Build] La receta esta vacia. No hay nada que construir.")
            return

        print("Iniciando construcción del Rig...")
        print(module_specs.describe_recipe(recipe))

        # El total de pasos ya no es una constante que haya que acordarse de
        # actualizar a mano: sale de la propia receta.
        # La plantilla sale de la receta: con modulos del caballo, los pasos
        # fijos del biped (body, chest, hip) no se ejecutan.
        self.template = module_specs.infer_template(recipe)

        core_steps = [step for step in self.CORE_STEPS
                      if step[1] not in self.skip_core
                      and (step[3] is None or self.template in step[3])]

        print(f"[Build] Plantilla: {self.template}")
        total = len(recipe) + len(core_steps)

        if not show_progress:
            prog = progress_module.RigProgress(total=total)
            prog.enabled = False
            return self._build_steps(prog, recipe, core_steps)

        with progress_module.rig_progress(
                title="La monja gitana autorig",
                total=total,
                mode="window") as prog:
            self._build_steps(prog, recipe, core_steps)

        print("Rig construido.")

    @staticmethod
    def default_recipe(template=None):
        """
        Una plantilla entera con las features por defecto de cada modulo.

        Sin template se usa la de por defecto (biped). Antes recorria TODOS los
        modulos de la tabla, y ahora eso mezclaria el biped con el caballo:
        dos espinas, dos cuellos y guias que chocan de nombre.
        """
        template = template or module_specs.DEFAULT_TEMPLATE

        recipe = []
        for module_type in module_specs.module_types(template):
            for side in module_specs.module_sides(module_type):
                recipe.append({
                    "type": module_type,
                    "side": side,
                    "features": module_specs.default_feature_keys(module_type),
                })
        return recipe

    # ------------------------------------------------------------------
    # BUCLE PRINCIPAL
    # ------------------------------------------------------------------
    def _build_steps(self, prog, recipe, core_steps=None):
        """
        Mezcla los pasos fijos y los modulos de la receta en una sola lista
        ordenada, y la recorre. El orden NO es el orden en que el usuario ha
        pinchado los botones de la ventana: es el orden real que exige el rig
        (el chest antes que la clavicula del brazo, el hip antes que la pierna).
        """
        self.recipe = recipe
        self.modules = {}

        if core_steps is None:
            core_steps = self.CORE_STEPS

        timeline = []   # (orden, etiqueta, callable)

        for order, method_name, label, _templates in core_steps:
            timeline.append((order, label, getattr(self, method_name)))

        for entry in recipe:
            order = module_specs.MODULE_SPECS[entry["type"]]["order"]
            label = "{} {}".format(module_specs.module_label(entry["type"]),
                                   entry["side"])
            timeline.append((order, label, partial(self._build_module, entry)))

        timeline.sort(key=lambda step: step[0])

        for order, label, function in timeline:
            prog.step(label)
            function()

    #: Guia de la que depende cada modulo de extremidad, por lado. Si no esta,
    #: el modulo se salta con un aviso en vez de tumbar el build entero en un
    #: cmds.xform. Los modulos de cara ya comprueban sus guias por su cuenta.
    REQUIRED_GUIDES = {
        "arm":    "{side}_clavicule",
        "finger": "{side}_wrist",
        "leg":    "{side}_hip",
        "toe":    "{side}_ball",
    }

    def _missing_guide(self, entry):
        """Nombre de la guia que falta para esta entrada, o None si esta todo."""
        pattern = self.REQUIRED_GUIDES.get(entry["type"])
        if not pattern:
            return None

        guide = pattern.format(side=entry["side"])

        return None if cmds.objExists(guide) else guide

    def _build_module(self, entry):
        """Construye un modulo de la receta con su set de features."""
        missing = self._missing_guide(entry)
        if missing:
            hint = (" Dale a MIRROR, o comprueba que existe la guia del lado L."
                    if entry["side"] == "R" else "")
            cmds.warning("[Build] {} {}: no existe la guia '{}'. Se salta este "
                         "modulo.{}".format(module_specs.module_label(entry["type"]),
                                            entry["side"], missing, hint))
            self.modules[(entry["type"], entry["side"])] = None
            return

        builders = {
            "spine":  self._build_spine,
            "horse_spine": self._build_horse_spine,
            "horse_neck":  self._build_horse_neck,
            "horse_leg":      self._build_horse_leg,
            "horse_back_leg": self._build_horse_back_leg,
            "horse_tail":     self._build_horse_tail,
            "neck":   self._build_neck,
            "arm":    self._build_arm,
            "finger": self._build_finger,
            "leg":    self._build_leg,
            "toe":    self._build_toe,
            "mouth":   self._build_mouth,
            "jaw":     self._build_jaw,
            "eyebrow": self._build_eyebrow,
            "eye":     self._build_eye,
            "nose":    self._build_nose,
            "socket":  self._build_socket,
        }

        builder = builders.get(entry["type"])
        if builder is None:
            cmds.warning("[Build] No hay constructor para '{}'.".format(entry["type"]))
            return

        instance = builder(entry["side"], entry["features"])
        self.modules[(entry["type"], entry["side"])] = instance

    def get_module(self, module_type, side):
        return self.modules.get((module_type, side))

    # ==================================================================
    # CONSTRUCTORES DE MODULO
    # ==================================================================
    def _build_spine(self, side, features):
        self.spine_rig = spine_module.SpineModule(
            root_guide="root",
            chest_guide="chest",
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
        )
        self.spine_rig.build()
        return self.spine_rig

    def _build_arm(self, side, features):
        """
        El brazo ya sabe leer su propio set de features: curvature, twist y los
        atributos condicionales pasan dentro de LimbModule.build(). El soft IK
        y el pv pin se dejan para post_build(), que va despues del skinning.
        """
        arm_rig = limbs_module.LimbModule(
            shoulder_guide=f"{side}_shoulder",
            elbow_guide=f"{side}_elbow",
            wrist_guide=f"{side}_wrist",
            clavicule_guide=f"{side}_clavicule",
            rig_name="Arm",
            side=side,
            root_instance=self.root_rig,
            features=features,
        )
        arm_rig.build()
        return arm_rig

    def _build_finger(self, side, features):
        # La feature 'ik' la resuelve FingersModule por dentro: decide si
        # instancia fingersIk_module o no.
        fingers_rig = fingers_module.FingersModule(
            wrist_guide=f"{side}_wrist",
            rig_name="Arm",
            side=side,
            root_instance=self.root_rig,
            features=features,
        )
        fingers_rig.build()

        # Los atributos extra de la mano van aparte porque necesitan los
        # controles FK y sus grupos _SDK ya creados. Cada uno (fan, spread,
        # fist) es una feature independiente.
        extra_attrs = [attr for attr
                       in extraFingerAttributes_module.FingersExtraModule.ALL_ATTRIBUTES
                       if attr in features]

        if extra_attrs:
            extra = extraFingerAttributes_module.FingersExtraModule(
                rig_name="Arm",
                side=side,
                fingers_module=fingers_rig,
                attributes=extra_attrs,
            )
            extra.build()
            fingers_rig.extra_attrs = extra
        else:
            print(f"[{side}_Arm fingers] Sin atributos extra en la receta.")

        return fingers_rig

    def _build_leg(self, side, features):
        leg_rig = leg_module.LegModule(
            thigh_guide=f"{side}_hip",
            knee_guide=f"{side}_knee",
            ankle_guide=f"{side}_ankle",
            ball_guide=f"{side}_ball",
            tip_guide=f"{side}_toe_tip",
            heel_guide=f"{side}_heel",
            rig_name="Leg",
            side=side,
            root_instance=self.root_rig,
            hip_instance=self.hip_rig,
            features=features,
        )
        leg_rig.build()

        # Los dedos del pie ya no se construyen aqui: son su propio modulo de
        # la receta ("toe"), con _build_toe.

        return leg_rig

    def _build_toe(self, side, features):
        """
        Dedos del pie. Modulo propio, como los dedos de la mano.

        Cuelgan de {side}_Leg_ball_bind_JNT, que lo crea la pierna. El orden de
        la receta ya pone "toe" (45) detras de "leg" (40), pero si en el arbol
        hay dedos del pie sin pierna de ese lado, no hay de donde colgarlos: se
        avisa y se salta, en vez de tumbar el build.
        """
        attach = f"{side}_Leg_ball_bind_JNT"

        if not cmds.objExists(attach):
            cmds.warning(f"[Toes {side}] No existe {attach}: los dedos del pie "
                         f"necesitan la pierna {side}. Anade Leg {side} al arbol. "
                         f"Se saltan los dedos del pie {side}.")
            return None

        toes_rig = toes_module.ToesModule(
            ball_guide=f"{side}_ball",
            tip_guide=f"{side}_toe_tip",
            heel_guide=f"{side}_heel",
            rig_name="Leg",
            side=side,
            root_instance=self.root_rig,
            features=features,
        )
        toes_rig.build()

        leg_rig = self.get_module("leg", side)
        if leg_rig is not None:
            leg_rig.toes = toes_rig

        return toes_rig

    # ==================================================================
    # PASOS FIJOS
    # ==================================================================
    def _core_root(self):
        # Se mide el personaje ANTES de crear el primer control. Todo lo que
        # venga despues coge el tamano de aqui, asi que ningun modulo necesita
        # saber lo grande que es el personaje.
        controlsLibrary.update_rig_scale_from_guides()

        self.root_rig = rigRoot_module.RigRoot(rig_name=self.RIG_NAME)
        self.root_rig.build()

    def _core_body(self):
        self.body_rig = body_module.BodyModule(
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
        )
        self.body_rig.build()

    def _core_chest(self):
        self.chest_rig = chest_module.ChestModule(
            chest_guide="chest",
            root_instance=self.root_rig,
        )
        self.chest_rig.build()

    # ==================================================================
    # CUADRUPEDO
    # ==================================================================
    def _build_horse_spine(self, side, features):
        """
        Espina del caballo.

        El COG NO lo crea este modulo: lo monta hip_module (paso 13, antes que
        la espina), que es el que hace el body_CTL con el pivote movible
        (translationFromMatrix -> rotatePivot y scalePivot) y el localHip_CTL.

        HorseSpine tiene su propio _build_body, pero es la version reducida
        para usar la espina suelta fuera del autorig. Con build_body=False
        coge el body_ctl que hip_module ha publicado en root_instance, que es
        de donde cuelgan sus controles.
        """
        missing = [guide for guide in horse_spine.HorseSpine.DEFAULT_GUIDES
                   if not cmds.objExists(guide)]
        if missing:
            cmds.warning(f"[Horse Spine] Faltan guias ({', '.join(missing)}). "
                         f"Se salta la espina.")
            return None

        if not getattr(self.root_rig, "body_ctl", None):
            cmds.warning("[Horse Spine] No hay body_CTL: los controles de la "
                         "espina no colgaran del COG. Revisa el paso Hip.")

        spine = horse_spine.HorseSpine(
            name="spine",
            root_instance=self.root_rig,
            build_body=False,
        )
        spine.build()

        self.horse_spine_rig = spine

        return spine

    def _build_horse_neck(self, side, features):
        """
        Cuello del caballo (ribbon).

        La base del cuello se constrine al joint del pecho de la espina, que
        se le pide a la instancia ya construida en vez de escribir el nombre a
        mano: si HorseSpine cambia su convencion, esto sigue valiendo.
        """
        missing = [guide for guide in ("neck_root", "neck_mid", "neck_end")
                   if not cmds.objExists(guide)]
        if missing:
            cmds.warning(f"[Horse Neck] Faltan guias ({', '.join(missing)}). "
                         f"Se salta el cuello.")
            return None

        spine = self.get_module("horse_spine", "C")
        parent_joint = None
        if spine is not None:
            parent_joint = (getattr(spine, "data", None) or {}).get("chest_jnt")

        if not parent_joint:
            cmds.warning("[Horse Neck] No encuentro el joint del pecho de la "
                         "espina: el cuello no la seguira.")

        # pin_joints: el modulo no crea ninguno por defecto. Con la feature
        # marcada se piden los 5 que reparte por la V del ribbon.
        neck = horse_neck.HorseNeck(
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
            parent_joint=parent_joint,
            pin_joints=5 if "pin_joints" in features else 0,
        )
        neck.build()

        self.horse_neck_rig = neck

        return neck

    def _horse_spine_control(self, key, fallback=None):
        """
        Un control de la espina del caballo, pedido a la instancia construida.

        key es "chest" para las patas de delante y "hip" para las de detras.
        Se lee de spine.data en vez de escribir "spine_chest_CTRL" a mano: si
        HorseSpine cambia su convencion de nombres, esto sigue valiendo.
        """
        spine = self.get_module("horse_spine", "C")
        data = getattr(spine, "data", None) or {}
        control = (data.get("controls", {}).get(key) or {}).get("ctrl")

        if control and cmds.objExists(control):
            return control

        cmds.warning(f"[Horse] No encuentro el control '{key}' de la espina. "
                     f"Se usa {fallback}.")

        return fallback

    #: NURBS sobre la que se proyecta la escapula. Se buscan varios nombres
    #: porque la superficie puede venir de las guias o estar puesta a mano.
    THORAX_CANDIDATES = ("thorax_NRB", "Character_thorax_NRB", "thorax_surface")

    def _horse_thorax_surface(self):
        for name in self.THORAX_CANDIDATES:
            if cmds.objExists(name):
                return name

        cmds.warning("[Horse Front Leg] No encuentro la NURBS del torax "
                     f"({', '.join(self.THORAX_CANDIDATES)}). La escapula se "
                     f"construye sin proyeccion sobre las costillas.")

        return None

    def _build_horse_leg(self, side, features):
        """Pata delantera: con clavicula y casco."""
        required = [f"{side}_clavicule", f"{side}_clavicule_start",
                    f"{side}_hip", f"{side}_knee", f"{side}_ankle",
                    f"{side}_ball", f"{side}_toe_tip", f"{side}_heel",
                    f"{side}_hoof_in", f"{side}_hoof_out"]
        missing = [guide for guide in required if not cmds.objExists(guide)]
        if missing:
            cmds.warning(f"[Horse Front Leg {side}] Faltan guias "
                         f"({', '.join(missing)}). Se salta la pata.")
            return None

        leg = horse_leg_module.LegModule(
            clavicule_start_guide=f"{side}_clavicule_start",
            clavicule_guide=f"{side}_clavicule",
            thigh_guide=f"{side}_hip",
            knee_guide=f"{side}_knee",
            ankle_guide=f"{side}_ankle",
            ball_guide=f"{side}_ball",
            tip_guide=f"{side}_toe_tip",
            heel_guide=f"{side}_heel",
            bank_in_guide=f"{side}_hoof_in",
            bank_out_guide=f"{side}_hoof_out",
            rig_name="Leg",
            side=side,
            root_instance=self.root_rig,
            # La clavicula de la pata de delante sigue al pecho de la espina.
            clavicule_parent=self._horse_spine_control(
                "chest", f"{self.RIG_NAME}_chestFix_CTL"),
            clavicle=True,
            hoof=True,
            scapula="scapula" in features,
            # La NURBS del torax. Sin ella el modulo construye la escapula
            # igual, pero sin el proximityPin: solo sigue a su control, sin
            # deslizarse sobre las costillas.
            scapula_surface=self._horse_thorax_surface(),
        )
        leg.build()

        return leg

    def _build_horse_back_leg(self, side, features):
        """
        Pata trasera: tres huesos (maluc, babilla, garro, menudillo), IK de
        muelle y sin clavicula. El legRoot cuelga de la pelvis.
        """
        required = [f"{side}_hip_back", f"{side}_knee_back",
                    f"{side}_hock_back", f"{side}_ankle_back",
                    f"{side}_ball_back", f"{side}_toe_tip_back",
                    f"{side}_heel_back",
                    f"{side}_hoof_in_back", f"{side}_hoof_out_back"]
        missing = [guide for guide in required if not cmds.objExists(guide)]
        if missing:
            cmds.warning(f"[Horse Back Leg {side}] Faltan guias "
                         f"({', '.join(missing)}). Se salta la pata.")
            return None

        leg = horse_leg_module.LegModule(
            thigh_guide=f"{side}_hip_back",
            knee_guide=f"{side}_knee_back",
            hock_guide=f"{side}_hock_back",
            ankle_guide=f"{side}_ankle_back",
            ball_guide=f"{side}_ball_back",
            tip_guide=f"{side}_toe_tip_back",
            heel_guide=f"{side}_heel_back",
            bank_in_guide=f"{side}_hoof_in_back",
            bank_out_guide=f"{side}_hoof_out_back",
            rig_name="BackLeg",
            side=side,
            root_instance=self.root_rig,
            # Sin clavicula, clavicule_parent es de quien cuelga el legRoot:
            # el control de la cadera de la espina.
            clavicule_parent=self._horse_spine_control(
                "hip", f"{self.RIG_NAME}_localHip_CTL"),
            clavicle=False,
            three_bone=True,
            hoof=True,
        )
        leg.build()

        return leg

    def _horse_leg_post_build(self, leg, entry):
        """
        Soft IK de las patas del caballo.

        horse_leg_module anade el canal .Soft al legIk_CTRL pero no monta la
        red: en el biped eso lo hace el post_build() del modulo, y el del
        caballo no lo tiene. Sin esto, el atributo existe y no hace nada.

        TODO: lo limpio seria darle un post_build() a horse_leg_module, como
        tienen LimbModule y LegModule del biped, y borrar este metodo.
        """
        import soft_module

        side = entry["side"]
        prefix = f"{side}_{leg.rig_name}"

        ik_chain = getattr(leg, "ik_chain", None)
        if not ik_chain:
            cmds.warning(f"[{prefix}] Sin cadena IK: no se monta el soft.")
            return None

        # i_ankle es el indice del menudillo: 2 en la pata delantera y 3 en la
        # trasera, que tiene un hueso mas.
        ankle_index = getattr(leg, "i_ankle", 2)

        if ankle_index > 2:
            cmds.warning(f"[{prefix}] Pata de tres huesos: el soft mide la "
                         f"cadena con dos segmentos, asi que la distancia "
                         f"maxima se queda corta. Revisalo al animar.")

        goal_ctrl = f"{prefix}_footBall_CTRL"

        leg.soft_result = soft_module.SoftIkModule(
            side=side, prefix=leg.rig_name
        ).apply_soft_ik(
            ik_ctrl=f"{prefix}_legIk_CTRL",
            ik_handle=f"{prefix}_IKH",
            ik_hdl=f"{prefix}_IKH",
            root_ctrl=f"{prefix}_legRoot_CTRL",
            root_jnt=ik_chain[0],
            mid_jnt=ik_chain[1],
            low_jnt=ik_chain[ankle_index],
            global_ctrl=f"{self.RIG_NAME}_global_CTL",
            # Quien manda sobre el ik handle es la cadena del reverse foot, no
            # el ik_ctrl: el goal es el control de la bola.
            goal_ctrl=goal_ctrl if cmds.objExists(goal_ctrl) else None,
        )

        return leg.soft_result

    def _build_horse_tail(self, side, features):
        """
        Cua FK. La base sigue a la pelvis de la espina.

        El joint se pide a la instancia (spine.data["pelvis"]) en vez de
        escribir "spine_pelvis_JNT" a mano.
        """
        guides = [f"tail_{i + 1:02d}" for i in range(5)]
        missing = [guide for guide in guides if not cmds.objExists(guide)]
        if missing:
            cmds.warning(f"[Horse Tail] Faltan guias ({', '.join(missing)}). "
                         f"Se salta la cola.")
            return None

        spine = self.get_module("horse_spine", "C")
        pelvis = (getattr(spine, "data", None) or {}).get("pelvis")

        if not pelvis:
            cmds.warning("[Horse Tail] No encuentro la pelvis de la espina: "
                         "la cola no la seguira.")

        tail = horse_tail.HorseTail(
            guides=guides,
            rig_name=self.RIG_NAME,
            parent_joint=pelvis,
            root_instance=self.root_rig,
        )
        tail.build()

        return tail

    def _build_neck(self, side, features):
        """
        Cuello y cabeza. Antes era un paso fijo; ahora es un modulo de la
        receta y solo se construye si esta en el arbol.

        Quien depende de el lo lleva bien si falta: los faciales avisan y no
        siguen a la cabeza, y los space switches se saltan el espacio "Head".
        """
        if not (cmds.objExists("neck_root") and cmds.objExists("neck_end")):
            cmds.warning("[Neck] No hay guias de cuello (neck_root / neck_end). "
                         "Se salta el cuello.")
            return None

        self.neck_rig = neck_module.NeckModule(
            neck_root="neck_root",
            neck_end="neck_end",
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
        )
        self.neck_rig.build()

        return self.neck_rig

    #: Guia de la que sale el hip/COG en cada plantilla.
    HIP_GUIDE = {"biped": "root", "quadruped": "spine_root"}

    def _core_hip(self):
        """
        Hip local + body (el COG con pivote movible).

        Es quien publica root_instance.body_ctl, del que cuelgan los controles
        de la espina en las dos plantillas. Por eso va antes que ella: hip es
        el paso 13 y la espina del caballo el 15.
        """
        guide = self.HIP_GUIDE.get(self.template, "root")

        if not cmds.objExists(guide):
            cmds.warning(f"[Hip] No existe la guia '{guide}'. Sin ella no hay "
                         f"body_CTL ni COG_CTRL. Se salta el hip.")
            return None

        # El del caballo monta el body entero (el COG con pivote movible); el
        # del biped espera que body_module ya lo haya creado.
        module = hip_module
        if self.template == "quadruped":
            if horse_hip_module is None:
                cmds.warning(
                    "[Hip] Falta horse_hip_module.py. Guarda ahi el hip del "
                    "caballo (el que crea el body con build_body) y vuelve a "
                    "cargar. Con el del biped no habra COG.")
                return None
            module = horse_hip_module

        self.hip_rig = module.HipModule(
            root_guide=guide,
            root_instance=self.root_rig,
        )
        self.hip_rig.build()

        return self.hip_rig

    # ==================================================================
    # CARA
    #
    # Antes iba todo junto en un paso fijo, se construyese o no. Ahora son
    # cuatro modulos de la receta como cualquier otro, con su lado y su sitio
    # en el arbol de la ventana.
    #
    # Cada uno comprueba sus guias antes de empezar: en una escena de prueba
    # donde solo estan las del brazo, la boca se salta con un aviso en vez de
    # tirar el build entero.
    # ==================================================================
    def _build_mouth(self, side, features):
        """
        Boca (SimpleMouthModule). Una sola instancia para los dos lados.

        Ya no necesita boca_surface: la cadena sale de cuatro guias, que solo
        existen en +X (el lado R se espeja en X dentro del modulo).
        """
        needed = ["C_lip_mid", "L_lip_end", "L_lip_in01", "L_lip_in02"]
        missing = [guide for guide in needed if not cmds.objExists(guide)]
        if missing:
            cmds.warning(f"[Mouth] Faltan guias ({', '.join(missing)}). "
                         f"Se salta la boca.")
            return None

        mouth = mouthModule.SimpleMouthModule(
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
            lip_mid="C_lip_mid",
            lip_end="L_lip_end",
            lip_in01="L_lip_in01",
            lip_in02="L_lip_in02",
            sides=("L", "R"),
        )

        # Las dos capas opcionales del modulo son flags de instancia, no
        # argumentos: se ajustan antes de build().
        mouth.use_cascade = "cascade" in features
        mouth.corner_upper_lower_attr = "corner_attr" in features

        # build() intenta engancharse al jaw. Como la boca va antes (50 < 52),
        # aqui todavia no hay jaw y lo avisa: es esperado, _build_jaw lo
        # engancha despues.
        mouth.build()

        self.mouth_rig = mouth

        return mouth

    def _build_jaw(self, side, features):
        if not (cmds.objExists("jaw_root") and cmds.objExists("jaw_end")):
            cmds.warning("[Jaw] No hay guias de mandibula. Se salta.")
            return None

        # mouth_instances vacio a proposito. Esa lista era para la MouthModule
        # vieja: el jaw le leia la comisura (end_lip_ctrl) y las curvas de
        # pinch. La SimpleMouthModule no tiene nada de eso; la relacion va al
        # reves, es la boca la que cuelga del jaw (attach_to_jaw, abajo).
        self.jaw_rig = jaw_module.JawModule(
            jaw_root="jaw_root",
            jaw_end="jaw_end",
            root_instance=self.root_rig,
            rig_name=self.RIG_NAME,
            side="C",
            mouth_instances=[],
        )
        self.jaw_rig.build()

        # Ahora que existen jawUpper_CTRL y jawLower_CTRL, se engancha la boca.
        # attach_to_jaw() es idempotente: si ya estaba enganchada no repite.
        mouth = self.get_module("mouth", "C")
        if mouth is not None and hasattr(mouth, "attach_to_jaw"):
            if not mouth.attach_to_jaw():
                cmds.warning("[Jaw] No se ha podido enganchar la boca: no "
                             "encuentro jawUpper_CTRL / jawLower_CTRL.")

        return self.jaw_rig

    def _build_eyebrow(self, side, features):
        if not cmds.objExists(f"{side}_eyebrow_root_01"):
            cmds.warning(f"[Eyebrow {side}] No hay guias de ceja. Se salta.")
            return None

        eyebrows = eyebrowsModule.EyebrowsModule(
            guide_prefix=f"{side}_eyebrow_root",
            num_joints=10,
            rig_name=self.RIG_NAME,
            side=side,
            root_instance=self.root_rig,
        )
        eyebrows.build()

        return eyebrows

    def _build_eye(self, side, features):
        # El ojo es el unico modulo que necesita un paso a mano ANTES del
        # build: seleccionar el edge loop del parpado y crear la curva desde la
        # seccion "Eye loop curves" de la ventana. Sin esas dos curvas no hay
        # de donde sacar ni la linea del parpado ni los joints de loop.
        #
        # El nombre no se escribe aqui: se lo pedimos al propio modulo, que es
        # quien manda sobre la convencion.
        missing = [
            eyes_module.EyesModule.loop_curve_name(side, self.RIG_NAME, upper=upper)
            for upper in (True, False)
            if not cmds.objExists(
                eyes_module.EyesModule.loop_curve_name(side, self.RIG_NAME, upper=upper))
        ]

        if missing:
            cmds.warning(f"[Eye {side}] Faltan curvas de loop ({', '.join(missing)}). "
                         f"Creala seleccionando el edge del parpado en la seccion "
                         f"'Eye loop curves'. Se salta el ojo {side}.")
            return None

        eyes = eyes_module.EyesModule(
            root_instance=self.root_rig,
            rig_name=self.RIG_NAME,
            side=side,
            features=features,
        )
        eyes.build()

        return eyes

    def _build_nose(self, side, features):
        """Nariz. Una instancia para los dos lados, como la boca."""
        nose = nose_module.NoseModule(
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
            features=features,
        )

        # build() comprueba sus guias y avisa si falta alguna.
        if nose.build() is None:
            return None

        return nose

    def _build_socket(self, side, features):
        """Socket del ojo. Un modulo por lado, como el ojo o la ceja."""
        socket = socket_module.SocketModule(
            rig_name=self.RIG_NAME,
            side=side,
            root_instance=self.root_rig,
            features=features,
        )

        # build() comprueba sus guias y avisa si falta alguna.
        if socket.build() is None:
            return None

        return socket

    def _core_skinning(self):
        skn = skinning_module.SkinningModule(
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
        )
        skn.build()

    # ------------------------------------------------------------------
    def _core_post(self):
        """
        Segunda pasada sobre los modulos ya construidos: soft IK y pole vector
        pins. Van despues del skinning, igual que antes.

        Brazos y piernas se resuelven solos: cada modulo tiene su post_build()
        y se sabe sus propios nombres de nodo. Los modulos que no tengan
        post_build() simplemente no hacen nada aqui.
        """
        for entry in self.recipe:
            instance = self.get_module(entry["type"], entry["side"])

            if instance is None:
                continue

            if hasattr(instance, "post_build"):
                instance.post_build()
            elif entry["type"] in ("horse_leg", "horse_back_leg"):
                # horse_leg_module no tiene post_build: su soft se monta aqui.
                self._horse_leg_post_build(instance, entry)

    # ------------------------------------------------------------------
    # def _existing_spaces(self, space_dict, target_control):
    #     """
    #     Quita del diccionario de espacios los que no existen en la escena.

    #     Antes todos los espacios se daban por hechos. Con modulos opcionales ya
    #     no: sin cuello no hay head_CTRL, y pasarle a SpaceModule un nodo que no
    #     existe tumbaria el build en el ultimo paso, con todo lo demas ya
    #     construido. Se avisa de cada espacio que se quita.
    #     """
    #     kept = {}
    #     for space_name, driver in space_dict.items():
    #         if cmds.objExists(driver):
    #             kept[space_name] = driver
    #         else:
    #             print(f"[Spaces] {target_control}: sin espacio '{space_name}' "
    #                   f"({driver} no existe).")
    #     return kept

    # def _core_spaces(self):
    #     """
    #     Dynamic parents. Esta parte ya era tolerante a que faltasen modulos
    #     gracias a los objExists, asi que sigue funcionando tal cual si el
    #     usuario construye un rig sin piernas o sin brazos.
    #     """
    #     print("[Spaces] Iniciando la creación de sistemas Dynamic Parent (_SPC)...")

    #     for side in ["L", "R"]:
    #         arm_ik_ctrl = f"{side}_Arm_armIk_CTRL"
    #         leg_ik_ctrl = f"{side}_Leg_legIk_CTRL"
    #         arm_pv_ctrl = f"{side}_Arm_poleVector_CTRL"
    #         leg_pv_ctrl = f"{side}_Leg_poleVector_CTRL"
    #         arm_fk_ctrl = f"{side}_Arm_shoulder_fk_CTRL"
    #         leg_fk_ctrl = f"{side}_Leg_thigh_fk_CTRL"

    #         if cmds.objExists(arm_ik_ctrl):
    #             spaceSwitching_module.SpaceModule(
    #                 target_control=arm_ik_ctrl,
    #                 space_dict=self._existing_spaces({
    #                     "MasterWalk": f"{self.RIG_NAME}_global_CTL",
    #                     "Chest": f"{self.RIG_NAME}_chestFix_CTL",
    #                     "Body": f"{self.RIG_NAME}_body_CTL",
    #                     "Hip": f"{self.RIG_NAME}_localHip_CTL",
    #                     "Head": f"{self.RIG_NAME}_head_CTRL",
    #                 }, arm_ik_ctrl),
    #                 attr_name="Space_Switch",
    #                 rig_name=self.RIG_NAME,
    #             ).build()
    #         else:
    #             print(f"[Spaces] ADVERTENCIA: No se encontró el control {arm_ik_ctrl}.")

    #         if cmds.objExists(leg_ik_ctrl):
    #             spaceSwitching_module.SpaceModule(
    #                 target_control=leg_ik_ctrl,
    #                 space_dict=self._existing_spaces({
    #                     "MasterWalk": f"{self.RIG_NAME}_global_CTL",
    #                     "Body": f"{self.RIG_NAME}_body_CTL",
    #                     "Hip": f"{self.RIG_NAME}_localHip_CTL",
    #                 }, leg_ik_ctrl),
    #                 attr_name="Space_Switch",
    #                 rig_name=self.RIG_NAME,
    #             ).build()

    #         if cmds.objExists(arm_pv_ctrl):
    #             spaceSwitching_module.SpaceModule(
    #                 target_control=arm_pv_ctrl,
    #                 space_dict=self._existing_spaces({
    #                     "MasterWalk": f"{self.RIG_NAME}_global_CTL",
    #                     "Body": f"{self.RIG_NAME}_body_CTL",
    #                     "Chest": f"{self.RIG_NAME}_chestFix_CTL",
    #                     "ArmIk": f"{side}_Arm_armIk_CTRL",
    #                     "Clavicule": f"{side}_Arm_clavicule_CTRL",
    #                 }, arm_pv_ctrl),
    #                 attr_name="Space_Switch",
    #                 rig_name=self.RIG_NAME,
    #             ).build()

    #         if cmds.objExists(leg_pv_ctrl):
    #             spaceSwitching_module.SpaceModule(
    #                 target_control=leg_pv_ctrl,
    #                 space_dict=self._existing_spaces({
    #                     "MasterWalk": f"{self.RIG_NAME}_global_CTL",
    #                     "Body": f"{self.RIG_NAME}_body_CTL",
    #                     "LegIk": f"{side}_Leg_legIk_CTRL",
    #                 }, leg_pv_ctrl),
    #                 attr_name="Space_Switch",
    #                 rig_name=self.RIG_NAME,
    #             ).build()

    #         if cmds.objExists(arm_fk_ctrl):
    #             spaceSwitching_module.SpaceModule(
    #                 target_control=arm_fk_ctrl,
    #                 space_dict=self._existing_spaces({
    #                     "Clavicule": f"{side}_Arm_clavicule_CTRL",
    #                     "Chest": f"{self.RIG_NAME}_chestFix_CTL",
    #                     "Body": f"{self.RIG_NAME}_body_CTL",
    #                 }, arm_fk_ctrl),
    #                 attr_name="Space_Switch",
    #                 rig_name=self.RIG_NAME,
    #             ).build()

    #         if cmds.objExists(leg_fk_ctrl):
    #             spaceSwitching_module.SpaceModule(
    #                 target_control=leg_fk_ctrl,
    #                 space_dict=self._existing_spaces({
    #                     "MasterWalk": f"{self.RIG_NAME}_global_CTL",
    #                     "Hip": f"{self.RIG_NAME}_localHip_CTL",
    #                     "Body": f"{self.RIG_NAME}_body_CTL",
    #                 }, leg_fk_ctrl),
    #                 attr_name="Space_Switch",
    #                 rig_name=self.RIG_NAME,
    #             ).build()

    #     # Los espacios de la cabeza solo tienen sentido si hay cabeza.
    #     if not cmds.objExists(f"{self.RIG_NAME}_head_CTRL"):
    #         print("[Spaces] No hay cuello en el rig: se saltan los espacios de "
    #               "la cabeza.")
    #         return

        # self.head_spaces = headSpace_module.HeadSpacesModule(
        #     rig_name=self.RIG_NAME,
        #     head_ctrl=f"{self.RIG_NAME}_head_CTRL",
        #     neck_ctrl=f"{self.RIG_NAME}_neck_CTRL",
        #     chest_ctrl=f"{self.RIG_NAME}_chestFix_CTL",
        #     body_ctrl=f"{self.RIG_NAME}_body_CTL",
        #     master_walk_ctrl=f"{self.RIG_NAME}_global_CTL",
        #     root_instance=self.root_rig,
        # )
        # self.head_spaces.build()