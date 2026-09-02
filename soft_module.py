import maya.cmds as cmds
import math
from nodeCreator_module import NodeCreator


class SoftIkModule(object):
    """Modulo centralizado para conectar redes de Soft IK en brazos y piernas."""

    def __init__(self, side="L", prefix="leg"):
        self.side = side
        self.prefix = f"{self.side}_{prefix}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_node(self, node_type, name, tag):
        """Helper para instanciar rapido usando tu NodeCreator."""
        creator = NodeCreator(
            side=self.side,
            node_type=node_type,
            base_name=self.prefix,
            name=name,
            tag=tag,
            parent=None,
            custom_suffix=None
        )
        return creator.create()

    def _parent_into_rig(self, node, parent_node):
        """
        Mete 'node' bajo 'parent_node' y le fuerza la escala local a 1.

        Lo segundo no es opcional: cmds.parent conserva la matriz de mundo, asi
        que si el padre ya viene escalado Maya compensa metiendo la inversa en
        la escala local del hijo, y el nodo se quedaria sin heredar el
        Global_Scale, que es justo lo que se busca aqui.
        """
        if not parent_node or not cmds.objExists(parent_node):
            cmds.warning(f"[{self.prefix}] Sin padre para {node}: el soft no heredara "
                         "el Global_Scale.")
            return node

        current = cmds.listRelatives(node, parent=True)
        if not current or current[0] != parent_node:
            cmds.parent(node, parent_node)

        for axis in "XYZ":
            cmds.setAttr(f"{node}.scale{axis}", 1)

        return node

    def _cleanup_previous_build(self):
        """
        Borra los transforms del soft de una construccion anterior.

        Sin esto, al reconstruir Maya autorenombra ('..._TRN1') y acabas con dos
        redes vivas peleandose por el mismo ikHandle.
        """
        for suffix in ("softGoal_TRN", "softOffset_TRN", "softTransform_TRN"):
            node = f"{self.prefix}_{suffix}"
            if cmds.objExists(node):
                cmds.delete(node)

    def _clear_handle_position_constraints(self, ik_hdl):
        """
        Quita cualquier point/parent/orientConstraint que este moviendo el
        ikHandle, para que el soft sea el unico que manda sobre su posicion.

        IMPORTANTE: el poleVectorConstraint tambien cuelga del handle, pero
        alimenta .poleVector, no .translate. Filtrando por las conexiones de
        translate/rotate nos lo saltamos y no se rompe el pole vector.
        """
        victims = set()
        for plug in ("translate", "rotate"):
            cons = cmds.listConnections(f"{ik_hdl}.{plug}",
                                        source=True, destination=False,
                                        type="constraint") or []
            for con in cons:
                if cmds.objectType(con) in ("pointConstraint",
                                            "parentConstraint",
                                            "orientConstraint"):
                    victims.add(con)

        for con in victims:
            cmds.warning(f"[{self.prefix}] Eliminando constraint previo sobre "
                         f"{ik_hdl}: {con}")
            cmds.delete(con)

    def _pick_up_vector(self, from_node, to_node):
        """
        Devuelve el eje de mundo mas perpendicular a la direccion del aim.

        En una pierna el goal cae casi en vertical bajo la raiz, asi que el
        (0,1,0) de toda la vida queda practicamente antiparalelo al aim: el
        aimConstraint entra en configuracion degenerada y el roll se vuelve
        loco. Eligiendo el eje menos alineado nos quitamos el problema tanto
        en brazos como en piernas sin tener que parametrizarlo.
        """
        a = cmds.xform(from_node, q=True, ws=True, t=True)
        b = cmds.xform(to_node, q=True, ws=True, t=True)
        vec = [b[i] - a[i] for i in range(3)]

        length = math.sqrt(sum(v * v for v in vec))
        if length < 1e-6:
            return (0, 1, 0)
        vec = [v / length for v in vec]

        candidates = [(0, 1, 0), (0, 0, 1), (1, 0, 0)]
        return min(candidates,
                   key=lambda c: abs(sum(c[i] * vec[i] for i in range(3))))

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def apply_soft_ik(self, ik_ctrl, ik_handle, mid_jnt, root_ctrl, low_jnt, global_ctrl, ik_hdl, root_jnt,
                      goal_ctrl=None):
        """
        Crea las conexiones de nodos para el Soft IK.

        Args:
            ik_ctrl (str): Nombre del control IK (donde esta el atributo .Soft).
            ik_handle (str): Alias historico de ik_hdl. Se mantiene en la firma
                para no tocar build_module.py, pero no se usa.
            root_jnt (str): El joint IK inicial de la cadena (Thigh o Shoulder).
            mid_jnt (str): El joint IK intermedio (Knee o Elbow).
            low_jnt (str): El joint IK final de la cadena (Ankle o Wrist).
            goal_ctrl (str): Quien mandaba sobre el ik handle ANTES de meter
                el soft. En un brazo es el propio ik_ctrl, y por eso es el
                valor por defecto. En una pierna NO lo es: ahi el handle iba
                pegado al footBall_CTRL, que cuelga de toda la cadena de
                pivotes del pie (ik_ctrl > heel > bankIn > bankOut > tip >
                ball). Si el soft apunta al ik_ctrl se salta esos pivotes y
                el foot roll deja de mover el tobillo.
        """
        # Por defecto el objetivo es el propio control IK (caso brazo).
        goal_ctrl = goal_ctrl or ik_ctrl

        self._cleanup_previous_build()

        # OJO: no se puede apuntar al goal_ctrl directamente. El ik handle
        # resuelve hasta el TOBILLO, y el footBall_CTRL esta en la bola del
        # pie: hay un offset real entre los dos. El parentConstraint que habia
        # antes del soft lo conservaba con mo=True; aqui hace falta lo mismo.
        #
        # Este TRN nace en la posicion de reposo del handle y se cuelga del
        # goal_ctrl con mo=True: es el goal_ctrl "trasladado" al sitio donde
        # de verdad tiene que acabar el handle. Sin esto el handle se clava
        # encima de la bola del pie y la pierna se encoge.
        # Los TRN del soft tienen que vivir en el MISMO espacio de escala que el
        # ikHandle. Sueltos en la raiz de la escena no heredan el Global_Scale, y
        # entonces: (a) el translateX normalizado nunca se vuelve a multiplicar por
        # la escala, y (b) el offset con mo=True del goal se queda horneado en
        # unidades sin escalar. Las dos cosas revientan la pierna al escalar.
        soft_parent = (cmds.listRelatives(ik_hdl, parent=True) or [None])[0]

        soft_goal_node = cmds.group(empty=True, name=f"{self.prefix}_softGoal_TRN")
        cmds.matchTransform(soft_goal_node, ik_hdl, pos=True, rot=True)
        self._parent_into_rig(soft_goal_node, soft_parent)
        cmds.parentConstraint(goal_ctrl, soft_goal_node, mo=True)

        # ----------------------------------------------------------------
        # ATRIBUTOS DEL CONTROL IK
        # ----------------------------------------------------------------

        # Asegurar que el atributo Soft existe, si no, lo creamos
        if not cmds.attributeQuery("Soft", node=ik_ctrl, exists=True):
            cmds.addAttr(ik_ctrl, ln="Soft", at="double", min=0, max=1, dv=0, k=True)

        # Multiplicadores de longitud por segmento. Son el floatB de los dos
        # floatMath de abajo: sin ellos el multiply se hace contra el 0 por
        # defecto y el fullLength sale 0, que era exactamente lo que rompia
        # toda la red.
        for attr_name in ("upperLengthMult", "lowerLengthMult"):
            if not cmds.attributeQuery(attr_name, node=ik_ctrl, exists=True):
                cmds.addAttr(ik_ctrl, ln=attr_name, at="float",
                             min=0.001, dv=1.0, k=True)

        # ----------------------------------------------------------------
        # 1. LONGITUD DE CADA SEGMENTO
        # ----------------------------------------------------------------

        upperLenghtMult_node = self._create_node("floatMath", "upperLengthMult", "FLM")
        lowerLenghtMult_node = self._create_node("floatMath", "lowerLengthMult", "FLM")
        cmds.setAttr(f"{upperLenghtMult_node}.operation", 2)  # Multiply
        cmds.setAttr(f"{lowerLenghtMult_node}.operation", 2)  # Multiply

        # 2. Leer el translateX de cada joint IK y "pegarlo" como valor fijo en Float A
        low_tx = abs(cmds.getAttr(f"{low_jnt}.translateX"))
        mid_tx = abs(cmds.getAttr(f"{mid_jnt}.translateX"))

        cmds.setAttr(f"{upperLenghtMult_node}.floatA", mid_tx)
        cmds.setAttr(f"{lowerLenghtMult_node}.floatA", low_tx)

        # 3. El multiplicador vivo en Float B
        cmds.connectAttr(f"{ik_ctrl}.upperLengthMult",
                         f"{upperLenghtMult_node}.floatB", force=True)
        cmds.connectAttr(f"{ik_ctrl}.lowerLengthMult",
                         f"{lowerLenghtMult_node}.floatB", force=True)

        # Suma de los dos segmentos: la longitud total de la extremidad estirada.
        fullLenght_node = self._create_node("floatMath", "FullLength", "FLM")  # default = Add
        cmds.connectAttr(f"{upperLenghtMult_node}.outFloat", f"{fullLenght_node}.floatA")
        cmds.connectAttr(f"{lowerLenghtMult_node}.outFloat", f"{fullLenght_node}.floatB")

        # ----------------------------------------------------------------
        # 4. DISTANCIA REAL ENTRE EL ROOT Y EL GOAL
        # ----------------------------------------------------------------

        # Se mide contra soft_goal_node, que es donde acaba el handle: la
        # distancia tiene que ser la misma que luego recorre el aim, o el soft
        # empieza a actuar a una longitud que no corresponde.
        #
        # El origen es root_ctrl y NO root_jnt a proposito: el root_jnt recibe
        # su rotacion del propio ikHandle, asi que meter su worldMatrix aqui
        # cerraria un ciclo de evaluacion.
        distance_node = self._create_node("distanceBetween", "rootToIk", "DIST")

        cmds.connectAttr(f"{root_ctrl}.worldMatrix[0]", f"{distance_node}.inMatrix1", force=True)
        cmds.connectAttr(f"{soft_goal_node}.worldMatrix[0]", f"{distance_node}.inMatrix2", force=True)

        # 5. Float math que divida la distancia total entre el global scale
        distanceToControlNormalized_node = self._create_node("floatMath", "distanceToControlNormalized", "FLM")
        cmds.setAttr(f"{distanceToControlNormalized_node}.operation", 3)  # Divide
        cmds.connectAttr(f"{distance_node}.distance", f"{distanceToControlNormalized_node}.floatA")

        if cmds.objExists(global_ctrl) and cmds.attributeQuery("Global_Scale", node=global_ctrl, exists=True):
            cmds.connectAttr(f"{global_ctrl}.Global_Scale",
                             f"{distanceToControlNormalized_node}.floatB", force=True)
        else:
            cmds.warning(f"[{self.prefix}] No encuentro {global_ctrl}.Global_Scale. "
                         "El soft no seguira la escala global.")
            cmds.setAttr(f"{distanceToControlNormalized_node}.floatB", 1.0)

        # ----------------------------------------------------------------
        # 6. SOFT MAX DISTANCE
        # ----------------------------------------------------------------

        # softMaxDistance = fullLength - initialDistance, y es un valor FIJO:
        # el margen que le queda a la extremidad desde su pose de reposo hasta
        # quedar completamente estirada. Si se conectase vivo se recalcularia
        # cada vez que mueves el control y el soft nunca llegaria a dispararse.
        full_length_value = cmds.getAttr(f"{fullLenght_node}.outFloat")
        initial_distance_value = cmds.getAttr(f"{distanceToControlNormalized_node}.outFloat")
        soft_max_distance = full_length_value - initial_distance_value

        # Si la extremidad se ha construido practicamente recta el margen es
        # cero y el soft no tendria recorrido. Damos un 5% de la longitud total
        # como minimo y avisamos, que suele significar guias mal flexionadas.
        min_margin = full_length_value * 0.05
        if soft_max_distance < min_margin:
            cmds.warning(f"[{self.prefix}] softMaxDistance calculado = {soft_max_distance:.4f}. "
                         f"La extremidad esta casi recta en pose de reposo; se usa "
                         f"{min_margin:.4f} (5% de la longitud). Revisa la flexion de las guias.")
            soft_max_distance = min_margin

        softMaxDistance_node = self._create_node("floatConstant", "softMaxDistance", "FLC")
        cmds.setAttr(f"{softMaxDistance_node}.inFloat", soft_max_distance)

        # ----------------------------------------------------------------
        # 7. SOFT VALUE
        # ----------------------------------------------------------------

        remapValue_node = self._create_node("remapValue", "softValue", "RMV")
        cmds.connectAttr(f"{ik_ctrl}.Soft", f"{remapValue_node}.inputValue")
        cmds.setAttr(f"{remapValue_node}.outputMin", 0.001)  # nunca 0: luego se divide por el
        cmds.connectAttr(f"{softMaxDistance_node}.outFloat",
                         f"{remapValue_node}.outputMax", force=True)

        # softDistance = fullLength - softValue
        softDistanceSubstact_node = self._create_node("floatMath", "softDistance", "FLM")
        cmds.setAttr(f"{softDistanceSubstact_node}.operation", 1)  # Subtract
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{softDistanceSubstact_node}.floatA")
        cmds.connectAttr(f"{remapValue_node}.outValue", f"{softDistanceSubstact_node}.floatB")

        # ----------------------------------------------------------------
        # 8. LA EXPONENCIAL
        # softConstant = softValue * (1 - e^-((dist - softDistance)/softValue)) + softDistance
        # ----------------------------------------------------------------

        distanceToControl_node = self._create_node("floatMath", "distanceToControlMinusSoftValue", "FLM")
        cmds.setAttr(f"{distanceToControl_node}.operation", 1)  # Subtract
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{distanceToControl_node}.floatA")
        cmds.connectAttr(f"{softDistanceSubstact_node}.outFloat", f"{distanceToControl_node}.floatB")

        softExponentDivision_node = self._create_node("floatMath", "softExponentDivision", "FLM")
        cmds.setAttr(f"{softExponentDivision_node}.operation", 3)  # Divide
        cmds.connectAttr(f"{distanceToControl_node}.outFloat", f"{softExponentDivision_node}.floatA")
        cmds.connectAttr(f"{remapValue_node}.outValue", f"{softExponentDivision_node}.floatB")

        softExponentDivisionNegate_node = self._create_node("floatMath", "softExponentDivisionNegate", "FLM")
        cmds.setAttr(f"{softExponentDivisionNegate_node}.operation", 2)  # Multiply
        cmds.connectAttr(f"{softExponentDivision_node}.outFloat", f"{softExponentDivisionNegate_node}.floatB")
        cmds.setAttr(f"{softExponentDivisionNegate_node}.floatA", -1)

        softExponent_node = self._create_node("floatMath", "softExponent", "FLM")
        cmds.setAttr(f"{softExponent_node}.operation", 6)  # Power
        cmds.connectAttr(f"{softExponentDivisionNegate_node}.outFloat", f"{softExponent_node}.floatB")
        cmds.setAttr(f"{softExponent_node}.floatA", math.e)

        oneMinusSoftExponent_node = self._create_node("floatMath", "oneMinusSoftExponent", "FLM")
        cmds.setAttr(f"{oneMinusSoftExponent_node}.operation", 1)  # Subtract
        cmds.connectAttr(f"{softExponent_node}.outFloat", f"{oneMinusSoftExponent_node}.floatB")
        cmds.setAttr(f"{oneMinusSoftExponent_node}.floatA", 1)

        oneMinusSoftExponentBySoftValue_node = self._create_node("floatMath", "oneMinusSoftExponentBySoftValue", "FLM")
        cmds.setAttr(f"{oneMinusSoftExponentBySoftValue_node}.operation", 2)  # Multiply
        cmds.connectAttr(f"{remapValue_node}.outValue", f"{oneMinusSoftExponentBySoftValue_node}.floatA")
        cmds.connectAttr(f"{oneMinusSoftExponent_node}.outFloat", f"{oneMinusSoftExponentBySoftValue_node}.floatB")

        softConstantAdd_node = self._create_node("floatMath", "softConstantAdd", "FLM")  # default = Add
        cmds.connectAttr(f"{oneMinusSoftExponentBySoftValue_node}.outFloat", f"{softConstantAdd_node}.floatA")
        cmds.connectAttr(f"{softDistanceSubstact_node}.outFloat", f"{softConstantAdd_node}.floatB")

        # ----------------------------------------------------------------
        # 9. PORCENTAJE DE ACCION DEL SOFT
        # ----------------------------------------------------------------

        softRatio_node = self._create_node("floatMath", "softRatio", "FLM")
        cmds.setAttr(f"{softRatio_node}.operation", 3)  # Divide
        cmds.connectAttr(f"{softConstantAdd_node}.outFloat", f"{softRatio_node}.floatA")
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{softRatio_node}.floatB")

        lengthRatio_node = self._create_node("floatMath", "lengthRatio", "FLM")
        cmds.setAttr(f"{lengthRatio_node}.operation", 3)  # Divide
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{lengthRatio_node}.floatA")
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{lengthRatio_node}.floatB")

        distanceToControlUnderLengthRatio_node = self._create_node("floatMath", "distanceToControlUnderLengthRatio", "FLM")
        cmds.setAttr(f"{distanceToControlUnderLengthRatio_node}.operation", 3)  # Divide
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{distanceToControlUnderLengthRatio_node}.floatA")
        cmds.connectAttr(f"{lengthRatio_node}.outFloat", f"{distanceToControlUnderLengthRatio_node}.floatB")

        softEffectorDistance_node = self._create_node("floatMath", "softEffectorDistanceMult", "FLM")
        cmds.setAttr(f"{softEffectorDistance_node}.operation", 2)  # Multiply
        cmds.connectAttr(f"{distanceToControlUnderLengthRatio_node}.outFloat", f"{softEffectorDistance_node}.floatA")
        cmds.connectAttr(f"{softRatio_node}.outFloat", f"{softEffectorDistance_node}.floatB")

        # ----------------------------------------------------------------
        # 10. SWITCH ENTRE COMPORTAMIENTOS
        # ----------------------------------------------------------------

        condition_node = self._create_node("condition", "softCondition", "COND")
        cmds.setAttr(f"{condition_node}.operation", 2)  # Greater Than
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{condition_node}.firstTerm")
        cmds.connectAttr(f"{softDistanceSubstact_node}.outFloat", f"{condition_node}.secondTerm")
        cmds.connectAttr(f"{softEffectorDistance_node}.outFloat", f"{condition_node}.colorIfTrueR")
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{condition_node}.colorIfFalseR")

        # ----------------------------------------------------------------
        # 11. CONECTAR EL SOFT AL HANDLE
        # ----------------------------------------------------------------

        # Crear TRNS y posicionarlos en la raiz de la cadena IK, para que el
        # softTransform viaje sobre la recta root -> destino real del handle.
        softOffset_node = cmds.group(empty=True, name=f"{self.prefix}_softOffset_TRN")
        softTransform_node = cmds.group(empty=True, name=f"{self.prefix}_softTransform_TRN")
        cmds.parent(softTransform_node, softOffset_node)
        cmds.matchTransform(softOffset_node, root_jnt, pos=True, rot=True)
        self._parent_into_rig(softOffset_node, soft_parent)

        # El TRN hijo tiene que arrancar en cero: su translateX es la salida
        # del condition, no un offset heredado del matchTransform.
        for axis in "XYZ":
            cmds.setAttr(f"{softTransform_node}.translate{axis}", 0)
            cmds.setAttr(f"{softTransform_node}.rotate{axis}", 0)
            cmds.setAttr(f"{softTransform_node}.scale{axis}", 1)

        cmds.pointConstraint(root_ctrl, softOffset_node, mo=False)

        # El aim va al soft_goal_node: asi el softTransform viaja sobre la
        # recta root -> destino real del handle, y todo lo que haga el foot
        # roll sigue llegando al tobillo.
        up_vector = self._pick_up_vector(root_ctrl, soft_goal_node)
        cmds.aimConstraint(soft_goal_node, softOffset_node, mo=False,
                           aimVector=(1, 0, 0), upVector=up_vector,
                           worldUpType="vector", worldUpVector=up_vector)

        # Conectar el resultado del condition al translateX del softTransform_node
        cmds.connectAttr(f"{condition_node}.outColorR", f"{softTransform_node}.translateX", force=True)

        # Se elimina el constraint que hubiera entre el ik hdl y su control
        # para sustituirlo por este. El poleVectorConstraint NO se toca.
        self._clear_handle_position_constraints(ik_hdl)
        cmds.pointConstraint(softTransform_node, ik_hdl, mo=False)

        # Tolerancia del solver muy baja para que el soft no tiemble
        if cmds.objExists("ikRPsolver"):
            cmds.setAttr("ikRPsolver.tolerance", 1e-08)

        print(f"[{self.prefix}] Soft IK conectado. fullLength={full_length_value:.4f} | "
              f"initialDistance={initial_distance_value:.4f} | "
              f"softMaxDistance={soft_max_distance:.4f}")

        return {
            "softTransform_node": softTransform_node,
            "softGoal_node": soft_goal_node,
            "softOffset_node": softOffset_node,
            "condition_node": condition_node,
            "fullLength_node": fullLenght_node,
            "softMaxDistance_node": softMaxDistance_node,
            "distanceToControl_node": distanceToControlNormalized_node
        }