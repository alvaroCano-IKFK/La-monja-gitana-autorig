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
import progress_module
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
        (12, "_core_neck",      "Cuello"),
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

    def _build_module(self, entry):
        """Construye un modulo de la receta con su set de features."""
        builders = {
            "spine":  self._build_spine,
            "arm":    self._build_arm,
            "finger": self._build_finger,
            "leg":    self._build_leg,
            "mouth":   self._build_mouth,
            "jaw":     self._build_jaw,
            "eyebrow": self._build_eyebrow,
            "eye":     self._build_eye,
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

        # Los dedos del pie van justo detras de la pierna: necesitan
        # {prefix}_ball_bind_JNT, y tienen que existir ANTES del skinning para
        # entrar en el esqueleto _ENV.
        if "toes" in features:
            toes_rig = toes_module.ToesModule(
                ball_guide=f"{side}_ball",
                tip_guide=f"{side}_toe_tip",
                heel_guide=f"{side}_heel",
                rig_name="Leg",
                side=side,
                root_instance=self.root_rig,
            )
            toes_rig.build()
            leg_rig.toes = toes_rig
        else:
            print(f"[{side}_Leg] Toes desactivado en la receta.")

        return leg_rig

    # ==================================================================
    # PASOS FIJOS
    # ==================================================================
    def _core_root(self):
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

    def _core_neck(self):
        self.neck_rig = neck_module.NeckModule(
            neck_root="neck_root",
            neck_end="neck_end",
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
        )
        self.neck_rig.build()

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
    @staticmethod
    def _mouth_class():
        """
        La clase de boca que haya en mouthModule.

        El contenido del modulo simple se pego dentro de mouthModule.py
        conservando el nombre de archivo, asi que la clase puede llamarse
        SimpleMouthModule o MouthModule segun como quedara el pegado. Se
        aceptan las dos para no depender de ese detalle.
        """
        for name in ("SimpleMouthModule", "MouthModule"):
            mouth_class = getattr(mouthModule, name, None)
            if mouth_class is not None:
                return mouth_class

        return None

    def _build_mouth(self, side, features):
        """
        El sistema simple construye LOS DOS LADOS de una vez.

        La receta puede traer una entrada de boca por lado. Si ya se construyo
        en la primera, la segunda devuelve la misma instancia en vez de montar
        todo otra vez encima: el modulo saca el lado R negando la X de la guia
        L, asi que no necesita una pasada por lado ni las guias del lado R.
        """
        mouth_class = self._mouth_class()
        if mouth_class is None:
            cmds.warning("[Mouth] No encuentro ninguna clase de boca en "
                         "mouthModule. Se salta.")
            return None

        existing = self.modules.get(("mouth", "L")) or self.modules.get(("mouth", "R"))
        if isinstance(existing, mouth_class):
            print(f"[Mouth {side}] Ya construida en la otra pasada.")
            return existing

        # El sistema simple no usa la NURBS: lo que necesita son las guias.
        required = ["C_lip_mid", "L_lip_end", "L_lip_in01", "L_lip_in02"]
        missing = [guide for guide in required if not cmds.objExists(guide)]
        if missing:
            cmds.warning(f"[Mouth {side}] Faltan guias: {missing}. Se salta. "
                         f"Si vienes de una escena antigua, borra las guias y "
                         f"vuelve a crearlas: lip_in01 y lip_in02 son nuevas.")
            return None

        mouth = mouth_class(
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
            lip_mid="C_lip_mid",
            lip_end="L_lip_end",
            lip_in01="L_lip_in01",
            lip_in02="L_lip_in02",
        )
        mouth.build()

        return mouth

    def _build_jaw(self, side, features):
        if not (cmds.objExists("jaw_root") and cmds.objExists("jaw_end")):
            cmds.warning("[Jaw] No hay guias de mandibula. Se salta.")
            return None

        # La mandibula lee los controles de comisura de la boca. Se le pasan
        # las instancias que ya haya construido la receta; si no hay ninguna,
        # el modulo los busca por nombre en la escena como hacia antes.
        mouth_instances = [instance for (module_type, _), instance
                           in self.modules.items()
                           if module_type == "mouth" and instance is not None]

        self.jaw_rig = jaw_module.JawModule(
            jaw_root="jaw_root",
            jaw_end="jaw_end",
            root_instance=self.root_rig,
            rig_name=self.RIG_NAME,
            side="C",
            mouth_instances=mouth_instances,
        )
        self.jaw_rig.build()

        # La boca se puede haber construido ANTES que el jaw, y entonces sus
        # constraints contra la mandibula quedaron pendientes. Ahora los
        # controles del jaw ya existen, asi que se rematan. attach_to_jaw() es
        # idempotente, de modo que si ya se engancho no hace nada.
        for instance in mouth_instances:
            if hasattr(instance, "attach_to_jaw"):
                instance.attach_to_jaw()

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
                    space_dict={
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Chest": f"{self.RIG_NAME}_chestFix_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                        "Hip": f"{self.RIG_NAME}_localHip_CTL",
                        "Head": f"{self.RIG_NAME}_head_CTRL",
                    },
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()
            else:
                print(f"[Spaces] ADVERTENCIA: No se encontró el control {arm_ik_ctrl}.")

            if cmds.objExists(leg_ik_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=leg_ik_ctrl,
                    space_dict={
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                        "Hip": f"{self.RIG_NAME}_localHip_CTL",
                    },
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

            if cmds.objExists(arm_pv_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=arm_pv_ctrl,
                    space_dict={
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                        "Chest": f"{self.RIG_NAME}_chestFix_CTL",
                        "ArmIk": f"{side}_Arm_armIk_CTRL",
                        "Clavicule": f"{side}_Arm_clavicule_CTRL",
                    },
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

            if cmds.objExists(leg_pv_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=leg_pv_ctrl,
                    space_dict={
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                        "LegIk": f"{side}_Leg_legIk_CTRL",
                    },
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

            if cmds.objExists(arm_fk_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=arm_fk_ctrl,
                    space_dict={
                        "Clavicule": f"{side}_Arm_clavicule_CTRL",
                        "Chest": f"{self.RIG_NAME}_chestFix_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                    },
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

            if cmds.objExists(leg_fk_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=leg_fk_ctrl,
                    space_dict={
                        "MasterWalk": f"{self.RIG_NAME}_global_CTL",
                        "Hip": f"{self.RIG_NAME}_localHip_CTL",
                        "Body": f"{self.RIG_NAME}_body_CTL",
                    },
                    attr_name="Space_Switch",
                    rig_name=self.RIG_NAME,
                ).build()

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