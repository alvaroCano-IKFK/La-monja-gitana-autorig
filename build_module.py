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
    CORE_STEPS = [
        (0,  "_core_root",      "Root rig"),
        (1,  "_core_body",      "Body"),
        (11, "_core_chest",     "Chest"),
        (13, "_core_hip",       "Hip"),
        (70, "_core_skinning",  "Skinning"),
        (80, "_core_post",      "Soft IK y pole vector pins"),
        (90, "_core_spaces",    "Space switching"),
    ]

    # ------------------------------------------------------------------
    def __init__(self):
        self.modules = {}          # (tipo, lado) -> instancia construida
        self.recipe = []
        self.root_rig = None
        self.hip_rig = None
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
        core_steps = [step for step in self.CORE_STEPS
                      if step[1] not in self.skip_core]
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
    def default_recipe():
        """El biped entero con las features por defecto de cada modulo."""
        recipe = []
        for module_type in module_specs.module_types():
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

        for order, method_name, label in core_steps:
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

    def _core_hip(self):
        self.hip_rig = hip_module.HipModule(
            root_guide="root",
            root_instance=self.root_rig,
        )
        self.hip_rig.build()

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

            if instance is None or not hasattr(instance, "post_build"):
                continue

            instance.post_build()

    # ------------------------------------------------------------------
    def _existing_spaces(self, space_dict, target_control):
        """
        Quita del diccionario de espacios los que no existen en la escena.

        Antes todos los espacios se daban por hechos. Con modulos opcionales ya
        no: sin cuello no hay head_CTRL, y pasarle a SpaceModule un nodo que no
        existe tumbaria el build en el ultimo paso, con todo lo demas ya
        construido. Se avisa de cada espacio que se quita.
        """
        kept = {}
        for space_name, driver in space_dict.items():
            if cmds.objExists(driver):
                kept[space_name] = driver
            else:
                print(f"[Spaces] {target_control}: sin espacio '{space_name}' "
                      f"({driver} no existe).")
        return kept

    def _core_spaces(self):
        """
        Dynamic parents. Esta parte ya era tolerante a que faltasen modulos
        gracias a los objExists, asi que sigue funcionando tal cual si el
        usuario construye un rig sin piernas o sin brazos.
        """
        print("[Spaces] Iniciando la creación de sistemas Dynamic Parent (_SPC)...")

        for side in ["L", "R"]:
            arm_ik_ctrl = f"{side}_Arm_armIk_CTRL"
            leg_ik_ctrl = f"{side}_Leg_legIk_CTRL"
            arm_pv_ctrl = f"{side}_Arm_poleVector_CTRL"
            leg_pv_ctrl = f"{side}_Leg_poleVector_CTRL"
            arm_fk_ctrl = f"{side}_Arm_shoulder_fk_CTRL"
            leg_fk_ctrl = f"{side}_Leg_thigh_fk_CTRL"

            if cmds.objExists(arm_ik_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=arm_ik_ctrl,
                    space_dict=self._existing_spaces({
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Chest": f"{self.RIG_NAME}_chestFix_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                        "Hip": f"{self.RIG_NAME}_localHip_CTL",
                        "Head": f"{self.RIG_NAME}_head_CTRL",
                    }, arm_ik_ctrl),
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()
            else:
                print(f"[Spaces] ADVERTENCIA: No se encontró el control {arm_ik_ctrl}.")

            if cmds.objExists(leg_ik_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=leg_ik_ctrl,
                    space_dict=self._existing_spaces({
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                        "Hip": f"{self.RIG_NAME}_localHip_CTL",
                    }, leg_ik_ctrl),
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

            if cmds.objExists(arm_pv_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=arm_pv_ctrl,
                    space_dict=self._existing_spaces({
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                        "Chest": f"{self.RIG_NAME}_chestFix_CTL",
                        "ArmIk": f"{side}_Arm_armIk_CTRL",
                        "Clavicule": f"{side}_Arm_clavicule_CTRL",
                    }, arm_pv_ctrl),
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

            if cmds.objExists(leg_pv_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=leg_pv_ctrl,
                    space_dict=self._existing_spaces({
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                        "LegIk": f"{side}_Leg_legIk_CTRL",
                    }, leg_pv_ctrl),
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

            if cmds.objExists(arm_fk_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=arm_fk_ctrl,
                    space_dict=self._existing_spaces({
                        "Clavicule": f"{side}_Arm_clavicule_CTRL",
                        "Chest": f"{self.RIG_NAME}_chestFix_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                    }, arm_fk_ctrl),
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

            if cmds.objExists(leg_fk_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=leg_fk_ctrl,
                    space_dict=self._existing_spaces({
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Hip": f"{self.RIG_NAME}_localHip_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                    }, leg_fk_ctrl),
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

        # Los espacios de la cabeza solo tienen sentido si hay cabeza.
        if not cmds.objExists(f"{self.RIG_NAME}_head_CTRL"):
            print("[Spaces] No hay cuello en el rig: se saltan los espacios de "
                  "la cabeza.")
            return

        self.head_spaces = headSpace_module.HeadSpacesModule(
            rig_name=self.RIG_NAME,
            head_ctrl=f"{self.RIG_NAME}_head_CTRL",
            neck_ctrl=f"{self.RIG_NAME}_neck_CTRL",
            chest_ctrl=f"{self.RIG_NAME}_chestFix_CTL",
            body_ctrl=f"{self.RIG_NAME}_body_CTL",
            master_walk_ctrl=f"{self.RIG_NAME}_global_CTL",
            root_instance=self.root_rig,
        )
        self.head_spaces.build()