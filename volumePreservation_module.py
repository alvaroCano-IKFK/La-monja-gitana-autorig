# -*- coding: utf-8 -*-
"""
volumePreservation_module.py
============================

Volume preservation (squash & stretch) para una cadena de joints: la espina
del biped, y en principio cualquier cadena que cambie de longitud.

Sigue la infografia del curso (VOLUME PRESERVATION, tres paginas):

  1. SQUASH FACTOR
     squashCurve de grado 1 con un CV por joint, llevado por decomposeMatrix.
     curveInfo.arcLength / (longitud inicial * Global_Scale) = squashFactor.
     Se mide de los JOINTS y no de la curva del ikSpline porque el animador
     puede cambiar la longitud de cada tramo.

  2. FACTOR REMAP (uno por joint)
     Campana de 4 puntos (-1, 1, 1, -1) con interpolacion smooth. Falloff
     ensancha la meseta y MaxPos mueve el pico. inputValue = porcentaje del
     joint en la cadena. Dice CUANTO le afecta el volumen a cada joint.

  3. VOLUME REMAP (uno por joint)
     squashFactor -> escala de la seccion:
         minStretchLength -> minStretchEffect   (encogida: engorda)
         1                -> 1
         maxStretchLength -> maxStretchEffect   (estirada: adelgaza)
     con los extremos atenuados por el factor del paso 2.

  4. Un joint de salida hijo de cada joint de la cadena, con el resultado en
     las dos escalas de la seccion (X y Z en la espina, que va por Y).

Atributos:
  - En el control de ajustes (lo que ve el animador): VolumePreservation,
    Falloff, MaxPos.
  - En {rig}_{name}Settings_TRN (lo que no se le da al animador):
    maxStretchLength, minStretchLength, maxStretchEffect, minStretchEffect.

Ojo: si la cadena nunca cambia de longitud, el squashFactor vale 1 siempre y
esto no hace nada. En la espina hace falta la feature Stretch.
"""

import math

import maya.cmds as cmds

from nodeCreator_module import NodeCreator


class VolumePreservationModule(object):

    #: Valores por defecto del PDF.
    DEFAULTS = {
        "maxStretchLength": 2.0,
        "minStretchLength": 0.5,
        "maxStretchEffect": 0.5,
        "minStretchEffect": 2.0,
    }

    #: Escala minima de la seccion. Nunca 0 ni negativa.
    MIN_SCALE = 0.05

    #: Valores de la campana del factor remap, en orden de punto.
    FACTOR_VALUES = (-1.0, 1.0, 1.0, -1.0)

    def __init__(self, name, joints, settings_ctrl, rig_name="Character", side="C",
                 parent=None, scale_axes=("X", "Z"), global_scale=None):
        """
        Args:
            name (str): nombre corto de la cadena ("spine"). Da los nombres de
                los nodos: {rig_name}_{name}Settings_TRN, ...Squash_CRV...
            joints (list): la cadena, de la raiz a la punta. Tiene que cambiar
                de longitud (stretch) o el volumen no tiene nada que medir.
            settings_ctrl (str): control donde van los atributos del animador.
            parent (str): grupo del rig donde van el settings TRN y la
                squashCurve.
            scale_axes (tuple): ejes de la SECCION, o sea los dos que no son
                el eje del hueso.
            global_scale (str): plug del Global_Scale ("..._global_CTL.Global_Scale").
                None = la medida no se compensa con la escala global.
        """
        self.name = name
        self.joints = list(joints)
        self.settings_ctrl = settings_ctrl
        self.rig_name = rig_name
        self.side = side
        self.parent = parent
        self.scale_axes = tuple(axis.upper() for axis in scale_axes)
        self.global_scale = global_scale

        self.prefix = f"{rig_name}_{name}"

        self.settings_trn = None
        self.squash_curve = None
        self.squash_factor = None
        self.volume_joints = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _node(self, node_type, name, tag, suffix=None):
        return NodeCreator(side=self.side, node_type=node_type,
                           base_name=self.name, name=name, tag=tag,
                           parent=None, custom_suffix=suffix).create()

    def _float_math(self, name, tag, operation, a=None, b=None):
        """
        floatMath con A y B que pueden ser un plug (str) o un numero.
        operation: 0 add, 1 subtract, 2 multiply, 3 divide.
        """
        node = self._node("floatMath", name, tag)
        cmds.setAttr(f"{node}.operation", operation)
        for plug, value in (("floatA", a), ("floatB", b)):
            if value is None:
                continue
            if isinstance(value, str):
                cmds.connectAttr(value, f"{node}.{plug}")
            else:
                cmds.setAttr(f"{node}.{plug}", value)
        return f"{node}.outFloat"

    @staticmethod
    def _ws(node):
        return cmds.xform(node, q=True, ws=True, t=True)

    def _segment_lengths(self):
        positions = [self._ws(jnt) for jnt in self.joints]
        return [math.sqrt(sum((b[k] - a[k]) ** 2 for k in range(3)))
                for a, b in zip(positions[:-1], positions[1:])]

    @staticmethod
    def _add_attr(node, name, **kwargs):
        if not cmds.attributeQuery(name, node=node, exists=True):
            cmds.addAttr(node, ln=name, at="double", k=True, **kwargs)
        return f"{node}.{name}"

    def _volume_joint_name(self, joint):
        base = joint[:-4] if joint.endswith("_JNT") else joint
        return f"{base}_volume_JNT"

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self):
        self.joints = [jnt for jnt in self.joints if cmds.objExists(jnt)]
        if len(self.joints) < 2:
            cmds.warning(f"[{self.prefix} volume] Hacen falta 2 joints como minimo.")
            return None

        if not self.settings_ctrl or not cmds.objExists(self.settings_ctrl):
            cmds.warning(f"[{self.prefix} volume] No existe el control de ajustes "
                         f"'{self.settings_ctrl}'. No se monta el volumen.")
            return None

        if sum(self._segment_lengths()) < 1e-4:
            cmds.warning(f"[{self.prefix} volume] La cadena mide 0. No se monta.")
            return None

        self._cleanup_previous_build()

        user = self._animator_attributes()
        settings = self._settings_attributes()

        self.squash_factor = self._build_squash_factor()
        bounds = self._build_bounds(user)
        middle = self._build_volume_middle(settings)
        effects = self._build_effect_ranges(settings)

        for jnt, percent in zip(self.joints, self._percentages()):
            self.volume_joints.append(
                self._build_joint(jnt, percent, user, settings, bounds, middle, effects))

        print(f"[{self.prefix} volume] Volume preservation en "
              f"{len(self.volume_joints)} joints (escala {'/'.join(self.scale_axes)}).")

        return self.volume_joints

    def _cleanup_previous_build(self):
        for node in [f"{self.prefix}Settings_TRN", f"{self.prefix}Squash_CRV"] + \
                    [self._volume_joint_name(jnt) for jnt in self.joints]:
            if cmds.objExists(node):
                cmds.delete(node)

    def _percentages(self):
        """Posicion de cada joint en la cadena, de 0 a 1, por longitud."""
        lengths = self._segment_lengths()
        total = sum(lengths)
        percents, accumulated = [0.0], 0.0
        for length in lengths:
            accumulated += length
            percents.append(accumulated / total)
        return percents

    # ------------------------------------------------------------------
    # Atributos
    # ------------------------------------------------------------------
    def _animator_attributes(self):
        ctrl = self.settings_ctrl

        if not cmds.attributeQuery("volumeSep", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="volumeSep", nn="VOLUME", at="enum", en="------", k=False)
            cmds.setAttr(f"{ctrl}.volumeSep", channelBox=True)
            cmds.setAttr(f"{ctrl}.volumeSep", lock=True)

        return {
            # softMaxValue: el slider llega a 2. Se puede escribir mas, pero
            # por encima el adelgazamiento ya va contra el suelo de MIN_SCALE.
            "volume": self._add_attr(ctrl, "VolumePreservation", min=0, smx=2, dv=1),
            "falloff": self._add_attr(ctrl, "Falloff", min=0, max=1, dv=0),
            "max_pos": self._add_attr(ctrl, "MaxPos", min=0, max=1, dv=0.5),
        }

    def _settings_attributes(self):
        """
        Ajustes del rig, en un TRN que el animador no toca.

        minStretchLength y maxStretchLength no llegan a 1 por un pelo (0.99 /
        1.01): con los dos a 1 el tramo del volumeRemap mediria 0 y la
        division de _build_volume_middle reventaria.
        """
        trn = cmds.createNode("transform", n=f"{self.prefix}Settings_TRN")
        if self.parent and cmds.objExists(self.parent):
            trn = cmds.parent(trn, self.parent)[0]
        self.settings_trn = trn

        for attr in ("translate", "rotate", "scale"):
            for axis in "XYZ":
                cmds.setAttr(f"{trn}.{attr}{axis}", lock=True, keyable=False,
                             channelBox=False)

        d = self.DEFAULTS
        return {
            "max_length": self._add_attr(trn, "maxStretchLength", min=1.01,
                                         dv=d["maxStretchLength"]),
            "min_length": self._add_attr(trn, "minStretchLength", min=0.001, max=0.99,
                                         dv=d["minStretchLength"]),
            "max_effect": self._add_attr(trn, "maxStretchEffect", min=0, max=1,
                                         dv=d["maxStretchEffect"]),
            "min_effect": self._add_attr(trn, "minStretchEffect", min=1,
                                         dv=d["minStretchEffect"]),
        }

    # ------------------------------------------------------------------
    # 1. SQUASH FACTOR
    # ------------------------------------------------------------------
    def _build_squash_factor(self):
        positions = [self._ws(jnt) for jnt in self.joints]

        curve = cmds.curve(d=1, p=positions, n=f"{self.prefix}Squash_CRV")
        # En mundo: los CVs vienen de decomposeMatrix de worldMatrix.
        cmds.setAttr(f"{curve}.inheritsTransform", 0)
        if self.parent and cmds.objExists(self.parent):
            curve = cmds.parent(curve, self.parent, relative=True)[0]
        cmds.setAttr(f"{curve}.visibility", 0)
        self.squash_curve = curve

        shape = cmds.listRelatives(curve, shapes=True, noIntermediate=True)[0]

        for index, jnt in enumerate(self.joints):
            dcm = self._node("decomposeMatrix", f"squashPoint{index}", "world")
            cmds.connectAttr(f"{jnt}.worldMatrix[0]", f"{dcm}.inputMatrix")
            cmds.connectAttr(f"{dcm}.outputTranslate", f"{shape}.controlPoints[{index}]")

        info = self._node("curveInfo", "squash", "length", "CINF")
        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{info}.inputCurve")

        # La longitud inicial se calcula aqui y no con getAttr del arcLength:
        # es la misma (la curva es lineal por los joints) y no depende de que
        # el DG ya haya evaluado los decomposeMatrix.
        initial = sum(self._segment_lengths())

        scaled_initial = self._float_math("squashInitial", "scaled", 2,
                                          a=initial, b=self.global_scale or 1.0)
        if not self.global_scale:
            cmds.warning(f"[{self.prefix} volume] Sin Global_Scale: el volumen "
                         f"cambiara al escalar el personaje.")

        return self._float_math("squash", "factor", 3,
                                a=f"{info}.arcLength", b=scaled_initial)

    # ------------------------------------------------------------------
    # 2. FACTOR REMAP: los limites de la campana (compartidos)
    # ------------------------------------------------------------------
    def _build_bounds(self, user):
        """
        Las cuatro posiciones de la campana, que solo dependen de Falloff y
        MaxPos y por tanto se calculan una vez para todos los joints.

            lowBound  = remap(Falloff) de MaxPos a 0     -> punto 1
            punto 0   = 0 - lowBound
            highBound = remap(Falloff) de MaxPos a 1     -> punto 2
            punto 3   = 2 - highBound

        OJO con highBound: el texto del PDF dice "connect maxPos to the
        outputMax", pero asi, con Falloff a 0, el punto 2 caeria en 0 y los
        puntos quedarian desordenados. Su propia grafica pone los dos limites
        en MaxPos con Falloff 0: eso es outputMin = MaxPos y outputMax = 1,
        simetrico al lowBound.

        Asi la campana siempre vale 0 justo en los extremos de la cadena (0
        y 1) y 1 en MaxPos, y Falloff la va aplanando hasta 1 en todo.
        """
        low = self._node("remapValue", "lowBound", "falloff")
        cmds.connectAttr(user["falloff"], f"{low}.inputValue")
        cmds.connectAttr(user["max_pos"], f"{low}.outputMin")
        cmds.setAttr(f"{low}.outputMax", 0)

        high = self._node("remapValue", "highBound", "falloff")
        cmds.connectAttr(user["falloff"], f"{high}.inputValue")
        cmds.connectAttr(user["max_pos"], f"{high}.outputMin")
        cmds.setAttr(f"{high}.outputMax", 1)

        point0 = self._float_math("lowBound", "subtractInitial", 1,
                                  a=0.0, b=f"{low}.outValue")
        point3 = self._float_math("highBound", "subtractFinal", 1,
                                  a=2.0, b=f"{high}.outValue")

        return [point0, f"{low}.outValue", f"{high}.outValue", point3]

    # ------------------------------------------------------------------
    # 3. VOLUME REMAP: lo compartido
    # ------------------------------------------------------------------
    def _build_volume_middle(self, settings):
        """
        Donde cae la longitud 1 dentro del volumeRemap.

        El PDF pone los puntos directamente en 0.5, 1 y 2. Aqui el remap se
        normaliza (inputMin = minStretchLength, inputMax = maxStretchLength) y
        los puntos van en 0, medio y 1. El resultado es el mismo, pero no
        depende de como trate Maya una entrada por encima de 1, y estirar mas
        alla de maxStretchLength se queda clavado en maxStretchEffect.

            medio = (1 - minLength) / (maxLength - minLength)
        """
        numerator = self._float_math("volumeMiddle", "numerator", 1,
                                     a=1.0, b=settings["min_length"])
        denominator = self._float_math("volumeMiddle", "range", 1,
                                       a=settings["max_length"], b=settings["min_length"])
        return self._float_math("volumeMiddle", "position", 3,
                                a=numerator, b=denominator)

    def _build_effect_ranges(self, settings):
        """
        Lo que se aleja cada extremo de 1. Es el "isolate the effect without
        modifying the initial value" del PDF, sacado del bucle porque no
        depende del joint.
        """
        return {
            "min": self._float_math("minEffect", "isolate", 1,
                                    a=settings["min_effect"], b=1.0),   # minEffect - 1
            "max": self._float_math("maxEffect", "isolate", 1,
                                    a=1.0, b=settings["max_effect"]),   # 1 - maxEffect
        }

    # ------------------------------------------------------------------
    # Por joint
    # ------------------------------------------------------------------
    def _build_joint(self, jnt, percent, user, settings, bounds, middle, effects):
        index = self.joints.index(jnt)
        tag = f"joint{index}"

        # ---- factor remap ----
        factor = self._node("remapValue", "factor", tag)
        cmds.setAttr(f"{factor}.inputValue", percent)
        for point, (position, value) in enumerate(zip(bounds, self.FACTOR_VALUES)):
            cmds.connectAttr(position, f"{factor}.value[{point}].value_Position")
            cmds.setAttr(f"{factor}.value[{point}].value_FloatValue", value)
            cmds.setAttr(f"{factor}.value[{point}].value_Interp", 2)   # smooth

        # Con Falloff a 1 los puntos 0 y 1 coinciden en 0 y el joint de la
        # raiz podria leer el -1. El clamp lo deja en [0, 1].
        clamp = self._node("clamp", "factor", tag)
        cmds.connectAttr(f"{factor}.outValue", f"{clamp}.inputR")
        cmds.setAttr(f"{clamp}.minR", 0)
        cmds.setAttr(f"{clamp}.maxR", 1)

        # VolumePreservation escala el factor: 0 apaga, 1 es el de la campana.
        weight = self._float_math("factorWeight", tag, 2,
                                  a=f"{clamp}.outputR", b=user["volume"])

        # ---- extremos del volumeRemap ----
        squash_value = self._float_math("squashValue", tag, 0,
                                        a=self._float_math("squashEffect", tag, 2,
                                                           a=effects["min"], b=weight),
                                        b=1.0)                                  # 1 + (minEffect-1)*f
        stretch_raw = self._float_math("stretchValue", tag, 1,
                                       a=1.0,
                                       b=self._float_math("stretchEffect", tag, 2,
                                                          a=effects["max"], b=weight))  # 1 - (1-maxEffect)*f

        # Con VolumePreservation por encima de 2 (con el maxEffect por
        # defecto, 0.5), 1 - 0.5*f pasa a negativo: escala negativa, la
        # seccion se da la vuelta y la malla se rompe. Se le pone suelo.
        stretch_value = self._float_math("stretchValue", f"{tag}Floor", 5,
                                         a=stretch_raw, b=self.MIN_SCALE)   # max

        # ---- volume remap ----
        volume = self._node("remapValue", "volume", tag)
        cmds.connectAttr(self.squash_factor, f"{volume}.inputValue")
        cmds.connectAttr(settings["min_length"], f"{volume}.inputMin")
        cmds.connectAttr(settings["max_length"], f"{volume}.inputMax")

        cmds.setAttr(f"{volume}.value[0].value_Position", 0)
        cmds.connectAttr(squash_value, f"{volume}.value[0].value_FloatValue")

        cmds.connectAttr(middle, f"{volume}.value[1].value_Position")
        cmds.setAttr(f"{volume}.value[1].value_FloatValue", 1)

        cmds.setAttr(f"{volume}.value[2].value_Position", 1)
        cmds.connectAttr(stretch_value, f"{volume}.value[2].value_FloatValue")

        for point in range(3):
            cmds.setAttr(f"{volume}.value[{point}].value_Interp", 1)   # linear

        # ---- joint de salida ----
        cmds.select(clear=True)
        out = cmds.joint(n=self._volume_joint_name(jnt))
        # Relativo: se queda con los valores a cero, encima del padre.
        out = cmds.parent(out, jnt, relative=True)[0]
        for axis in self.scale_axes:
            cmds.connectAttr(f"{volume}.outValue", f"{out}.scale{axis}")

        return out