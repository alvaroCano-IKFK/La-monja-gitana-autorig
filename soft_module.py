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
        for suffix in ("softGoal_TRN", "softRoot_TRN", "softOffset_TRN", "softTransform_TRN"):
            node = f"{self.prefix}_{suffix}"
            if cmds.objExists(node):
                cmds.delete(node)

    #: Constraints que mueven un ikHandle y que el soft tiene que sustituir.
    POSITION_CONSTRAINTS = ("pointConstraint", "parentConstraint", "orientConstraint")

    def _clear_handle_position_constraints(self, ik_hdl):
        """
        Quita cualquier point/parent/orientConstraint que este moviendo el
        ikHandle, para que el soft sea el unico que manda sobre su posicion.

        SE PREGUNTA POR EL NODO ENTERO, no por "ik_hdl.translate".
        -----------------------------------------------------------
        Aqui estaba el fallo que rompia el caballo y no el biped. Un
        parentConstraint no se conecta al plug compuesto 'translate': se
        conecta a translateX, translateY y translateZ por separado. Y
        listConnections sobre un plug compuesto devuelve lo que entra en ESE
        plug, no lo que entra en sus hijos, asi que la version anterior no
        veia el constraint y lo dejaba vivo. Luego el pointConstraint del
        soft se encontraba el canal ocupado y Maya cortaba con "Object is
        already connected".

        Al biped no le pasaba porque a su handle no le llega ningun
        constraint cuando corre el post_build; a la pata del caballo si:
        horse_leg_module la engancha al footBall_CTRL para el reverse hoof.

        El poleVectorConstraint NO se toca: alimenta .poleVector, y filtrando
        por tipo se queda fuera.
        """
        incoming = cmds.listConnections(ik_hdl, source=True, destination=False,
                                        type="constraint") or []

        victims = {node for node in set(incoming)
                   if cmds.objectType(node) in self.POSITION_CONSTRAINTS}

        for node in victims:
            cmds.warning(f"[{self.prefix}] Eliminando constraint previo sobre "
                         f"{ik_hdl}: {node}")
            cmds.delete(node)

        # Por si quedara una conexion directa (sin constraint) en algun canal
        for axis in ("X", "Y", "Z"):
            plug = f"{ik_hdl}.translate{axis}"
            for source in cmds.listConnections(plug, source=True, destination=False,
                                               plugs=True) or []:
                cmds.warning(f"[{self.prefix}] Desconectando {source} -> {plug}")
                cmds.disconnectAttr(source, plug)

        return victims

    @staticmethod
    def _distance_between(node_a, node_b):
        """Distancia en el mundo entre dos nodos, en la pose actual."""
        a = cmds.xform(node_a, q=True, ws=True, t=True)
        b = cmds.xform(node_b, q=True, ws=True, t=True)

        return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))

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
                      goal_ctrl=None, soft_max_distance_override=None,
                      chain_joints=None, min_soft_ratio=0.0):
        """
        Crea las conexiones de nodos para el Soft IK.

        Args:
            ik_ctrl (str): Nombre del control IK (donde esta el atributo .Soft).
            ik_handle (str): Alias historico de ik_hdl. Se mantiene en la firma
                para no tocar build_module.py, pero no se usa.
            root_jnt (str): El joint IK inicial de la cadena (Thigh o Shoulder).
            mid_jnt (str): El joint IK intermedio (Knee o Elbow).
            low_jnt (str): El joint IK final de la cadena (Ankle o Wrist).
            root_ctrl (str): El control que mueve la raiz de la cadena. NO se
                usa para medir: solo para arrastrar el softRoot_TRN.
            goal_ctrl (str): Quien mandaba sobre el ik handle ANTES de meter
                el soft. En un brazo es el propio ik_ctrl, y por eso es el
                valor por defecto. En una pierna NO lo es: ahi el handle iba
                pegado al footBall_CTRL, que cuelga de toda la cadena de
                pivotes del pie (ik_ctrl > heel > bankIn > bankOut > tip >
                ball). Si el soft apunta al ik_ctrl se salta esos pivotes y
                el foot roll deja de mover el tobillo.
            soft_max_distance_override (float): Solo para casos raros. Si se
                pasa un valor mayor que (fullLength - initialDistance) el soft
                empezara a actuar YA en pose de reposo, asi que se recorta y
                se avisa.
            chain_joints (list): LA CADENA IK ENTERA, de la raiz al efector.
                Hace falta en cadenas de MAS DE DOS SEGMENTOS, como la pata
                trasera del cuadrupedo (maluc > babilla > garro > menudillo).
                Sin esto la longitud se calcula con mid_jnt y low_jnt, o sea
                solo dos segmentos, y en una pata de tres se deja uno entero
                fuera: la extremidad "mide" mucho menos de lo que mide y el
                soft nunca se dispara donde toca.
            min_soft_ratio (float): Recorrido MINIMO del soft, como fraccion
                de la longitud total. Para extremidades casi rectas en reposo
                (la pata de un caballo lo es, un brazo humano no), donde
                fullLength - initialDistance sale practicamente cero y el soft
                se queda sin margen. Ver la nota larga mas abajo.
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
        # RAIZ DEL SOFT
        # ----------------------------------------------------------------

        # Este transform es el equivalente al "group the start joint of the IK
        # chain" de la infografia, y es CRITICO que exista.
        #
        # No se puede medir desde root_jnt.worldMatrix porque el joint recibe
        # su rotacion del ikHandle y se cierra un ciclo de evaluacion. Pero
        # tampoco se puede medir desde root_ctrl: si el control no esta
        # exactamente encima del joint raiz, la distancia medida sale inflada
        # respecto al fullLength (que sale de los translateX de los joints), el
        # umbral del soft se dispara antes de tiempo y el codo se va hacia el
        # pole vector con el brazo quieto.
        #
        # La solucion es un transform en la posicion EXACTA del joint raiz,
        # arrastrado por el control con mo=True. Ni cicla ni miente.
        soft_root_node = cmds.group(empty=True, name=f"{self.prefix}_softRoot_TRN")
        cmds.matchTransform(soft_root_node, root_jnt, pos=True, rot=True)
        self._parent_into_rig(soft_root_node, soft_parent)
        cmds.parentConstraint(root_ctrl, soft_root_node, mo=True)

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

        # 2. LA LONGITUD DE CADA HUESO, MEDIDA EN EL MUNDO
        #
        # Antes esto leia el translateX de cada joint, dando por hecho que la
        # cadena esta orientada con la X a lo largo del hueso. En el biped lo
        # esta, porque sus joints se orientan con orientJoint. En el caballo
        # NO: horse_leg_module copia la orientacion de la GUIA con un
        # matchTransform, asi que la X apunta donde apunte la guia y la
        # longitud del hueso puede estar en la Y o en la Z.
        #
        # Resultado en el caballo: translateX = 0, fullLength = 0, y de ahi
        # para abajo toda la red con divisiones por cero. El condition sacaba
        # 0, el softTransform se quedaba clavado en la raiz y el ikHandle se
        # iba al hombro: la pata doblada sobre si misma.
        #
        # Midiendo la distancia real entre joints consecutivos da igual como
        # esten orientados. En una cadena bien orientada el numero es el
        # mismo que el translateX, asi que el biped no nota el cambio.
        if chain_joints and len(chain_joints) > 1:
            joints = list(chain_joints)
        else:
            joints = [root_jnt, mid_jnt, low_jnt]

        segments = [self._distance_between(a, b)
                    for a, b in zip(joints[:-1], joints[1:])]

        # "upper" se lleva todos los tramos menos el ultimo y "lower" el
        # ultimo. Con dos segmentos es exactamente el reparto de siempre.
        mid_tx = sum(segments[:-1])
        low_tx = segments[-1]

        print(f"[{self.prefix}] Huesos: {[round(v, 3) for v in segments]} "
              f"-> longitud {sum(segments):.3f}")

        if sum(segments) < 1e-4:
            cmds.error(f"[{self.prefix}] La cadena mide 0: no puedo montar el "
                       f"soft sin reventar la pata. Joints medidos: {joints}")

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
        # Y se mide DESDE soft_root_node, que esta sobre el joint raiz, para
        # que esta distancia y el fullLength (sacado de los translateX de los
        # joints) compartan origen. Si aqui entra root_ctrl y el control no
        # coincide con el joint, la comparacion del condition esta sesgada.
        distance_node = self._create_node("distanceBetween", "rootToIk", "DIST")

        cmds.connectAttr(f"{soft_root_node}.worldMatrix[0]", f"{distance_node}.inMatrix1", force=True)
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
        #
        # ESTE VALOR NO SE PUEDE INFLAR. Con softMaxDistance exacto se cumple
        # que softDistance = fullLength - softValue >= initialDistance para
        # cualquier Soft de 0 a 1, con igualdad justo en Soft = 1. Y en ese
        # limite la exponencial devuelve softConstant = softDistance =
        # distanceToControl. Traducido: en pose de reposo el brazo NO se mueve
        # con ningun valor de Soft.
        #
        # Si se le mete un margen mayor del real (por ejemplo forzando un 5%
        # "para que el soft tenga recorrido"), softDistance cae por debajo de
        # la distancia de reposo, el condition se pone en True con el brazo
        # quieto, el handle se retrae y el codo se va hacia el pole vector.
        # Ese es el pop.
        full_length_value = cmds.getAttr(f"{fullLenght_node}.outFloat")
        initial_distance_value = cmds.getAttr(f"{distanceToControlNormalized_node}.outFloat")

        # Red de seguridad: si por lo que sea la longitud sale cero, toda la
        # red de abajo divide por cero, el condition saca 0 y el handle se
        # clava en la raiz de la cadena. Mejor parar aqui que dejar la pata
        # doblada sobre si misma sin decir por que.
        if full_length_value < 1e-4:
            cmds.error(f"[{self.prefix}] fullLength = {full_length_value}. "
                       f"Revisa los multiplicadores upperLengthMult y "
                       f"lowerLengthMult de {ik_ctrl}.")
        safe_max_distance = max(0.0, full_length_value - initial_distance_value)

        soft_max_distance = safe_max_distance
        if soft_max_distance_override is not None:
            soft_max_distance = float(soft_max_distance_override)
            if soft_max_distance > safe_max_distance:
                cmds.warning(f"[{self.prefix}] El override {soft_max_distance:.4f} supera el "
                             f"maximo seguro {safe_max_distance:.4f}: el soft actuaria en pose "
                             "de reposo. Se recorta.")
                soft_max_distance = safe_max_distance

        # EXTREMIDADES RECTAS EN REPOSO
        # ------------------------------
        # softMaxDistance es el margen entre la pose de reposo y la extension
        # total. En un brazo o una pierna de biped, con su codo y su rodilla
        # flexionados, ese margen es de sobra. En la pata de un caballo NO: es
        # practicamente una columna recta, asi que el margen sale casi cero y
        # el soft no tiene por donde actuar. Es el caso de "le doy al Soft y
        # no pasa nada".
        #
        # Con min_soft_ratio se le da recorrido a la fuerza. EL PRECIO hay que
        # saberlo: el soft empieza a suavizar ANTES de la distancia de reposo,
        # asi que con Soft > 0 y la pata quieta, esta se recoge un pelin. Es
        # inevitable, no es un bug: suavizar la llegada al estiramiento total
        # significa empezar a frenar antes de llegar, y si en reposo ya estas
        # casi en el tope, ese "antes" cae dentro de la pose de reposo.
        #
        # Por eso va a 0 por defecto: el biped no lo necesita y no se entera.
        minimum = full_length_value * float(min_soft_ratio or 0.0)
        if minimum > soft_max_distance:
            cmds.warning(f"[{self.prefix}] La extremidad esta casi recta en reposo "
                         f"(margen real {soft_max_distance:.4f} sobre {full_length_value:.4f}). "
                         f"Se le fuerza un recorrido de {minimum:.4f} para que el soft haga "
                         f"algo; a cambio, con Soft > 0 la pata se recoge un poco en reposo.")
            soft_max_distance = minimum

        elif soft_max_distance < full_length_value * 0.01:
            cmds.warning(f"[{self.prefix}] softMaxDistance = {soft_max_distance:.4f} sobre una "
                         f"longitud de {full_length_value:.4f}. La extremidad esta casi recta en "
                         "pose de reposo, asi que el soft tendra recorrido nulo o casi nulo. "
                         "Flexiona mas las guias, o pasa min_soft_ratio.")

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

        # El softOffset nace y vive sobre el soft_root_node: el mismo punto
        # desde el que se mide la distancia. Asi el softTransform recorre
        # exactamente la recta rootJoint -> destino real del handle, y en el
        # cruce del condition las dos ramas valen lo mismo (sin salto).
        softOffset_node = cmds.group(empty=True, name=f"{self.prefix}_softOffset_TRN")
        softTransform_node = cmds.group(empty=True, name=f"{self.prefix}_softTransform_TRN")
        cmds.parent(softTransform_node, softOffset_node)
        cmds.matchTransform(softOffset_node, soft_root_node, pos=True, rot=True)
        self._parent_into_rig(softOffset_node, soft_parent)

        # El TRN hijo tiene que arrancar en cero: su translateX es la salida
        # del condition, no un offset heredado del matchTransform.
        for axis in "XYZ":
            cmds.setAttr(f"{softTransform_node}.translate{axis}", 0)
            cmds.setAttr(f"{softTransform_node}.rotate{axis}", 0)
            cmds.setAttr(f"{softTransform_node}.scale{axis}", 1)

        cmds.pointConstraint(soft_root_node, softOffset_node, mo=False)

        # El aim va al soft_goal_node: asi el softTransform viaja sobre la
        # recta root -> destino real del handle, y todo lo que haga el foot
        # roll sigue llegando al tobillo.
        up_vector = self._pick_up_vector(soft_root_node, soft_goal_node)
        cmds.aimConstraint(soft_goal_node, softOffset_node, mo=False,
                           aimVector=(1, 0, 0), upVector=up_vector,
                           worldUpType="vector", worldUpVector=up_vector)

        # Conectar el resultado del condition al translateX del softTransform_node
        cmds.connectAttr(f"{condition_node}.outColorR", f"{softTransform_node}.translateX", force=True)

        # Se elimina el constraint que hubiera entre el ik hdl y su control
        # para sustituirlo por este. El poleVectorConstraint NO se toca.
        #
        # NOTA: es un pointConstraint, no un parentConstraint. El handle deja
        # de heredar la rotacion del control, asi que la orientacion de la
        # muñeca/tobillo tiene que venir de su propio orientConstraint desde el
        # ik_ctrl (lo monta el limbs_module). Si no, el joint final se queda
        # con la orientacion congelada del momento del build.
        self._clear_handle_position_constraints(ik_hdl)

        try:
            cmds.pointConstraint(softTransform_node, ik_hdl, mo=False)
        except RuntimeError as error:
            driving = cmds.listConnections(ik_hdl, source=True, destination=False) or []
            cmds.error(f"[{self.prefix}] No puedo constrenir {ik_hdl} al soft "
                       f"({error}). Algo le sigue moviendo el translate: "
                       f"{sorted(set(driving))}")

        # Tolerancia del solver muy baja para que el soft no tiemble
        if cmds.objExists("ikRPsolver"):
            cmds.setAttr("ikRPsolver.tolerance", 1e-08)

        print(f"[{self.prefix}] Soft IK conectado. fullLength={full_length_value:.4f} | "
              f"initialDistance={initial_distance_value:.4f} | "
              f"softMaxDistance={soft_max_distance:.4f}")

        return {
            "softTransform_node": softTransform_node,
            "softGoal_node": soft_goal_node,
            "softRoot_node": soft_root_node,
            "softOffset_node": softOffset_node,
            "condition_node": condition_node,
            "fullLength_node": fullLenght_node,
            "softMaxDistance_node": softMaxDistance_node,
            "distanceToControl_node": distanceToControlNormalized_node
        }

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    def audit_soft(self, ik_ctrl):
        """
        Barre el atributo Soft de 0 a 1 y reporta la salida del condition.

        Con la red bien montada y la extremidad en pose de reposo, la salida
        tiene que ser IDENTICA para los cinco valores e igual a la
        distanceToControl. En cuanto empiece a bajar, el soft esta actuando en
        reposo y ahi tienes el pop.
        """
        # Los nombres no se escriben a mano: NodeCreator les pone su propio
        # prefijo y no tiene por que coincidir con self.prefix. Se buscan por
        # patron, que es lo que no se rompe si cambia la convencion.
        def find(tag):
            found = cmds.ls(f"*{self.prefix}*{tag}*") or []
            return found[0] if found else None

        cond = find("softCondition")
        dist = find("distanceToControlNormalized")
        soft_dist = find("softDistance")
        full = find("FullLength")

        if not all((cond, dist, soft_dist, full)):
            cmds.warning(f"[{self.prefix}] No encuentro la red del soft "
                         f"(condition={cond}, distance={dist}, "
                         f"softDistance={soft_dist}, fullLength={full}). "
                         f"Comprueba que el soft se ha construido para esta "
                         f"extremidad.")
            return

        original = cmds.getAttr(f"{ik_ctrl}.Soft")
        distance = cmds.getAttr(f"{dist}.outFloat")

        print(f"[{self.prefix}] fullLength={cmds.getAttr(f'{full}.outFloat'):.4f} | "
              f"distanceToControl={distance:.4f}")

        try:
            for value in (0.0, 0.25, 0.5, 0.75, 1.0):
                cmds.setAttr(f"{ik_ctrl}.Soft", value)
                out = cmds.getAttr(f"{cond}.outColorR")
                delta = out - distance
                flag = "" if abs(delta) < 1e-4 else "  <-- el soft actua en reposo"
                print(f"  Soft={value:.2f}  softDistance={cmds.getAttr(f'{soft_dist}.outFloat'):8.4f}"
                      f"  out={out:8.4f}  delta={delta:+.4f}{flag}")
        finally:
            cmds.setAttr(f"{ik_ctrl}.Soft", original)