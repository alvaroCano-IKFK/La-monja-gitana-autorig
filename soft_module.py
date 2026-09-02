import maya.cmds as cmds
import math
from nodeCreator_module import NodeCreator

class SoftIkModule(object):
    """Módulo centralizado para conectar redes de Soft IK en brazos y piernas."""

    def __init__(self, side="L", prefix="leg"):
        self.side = side
        self.prefix = f"{self.side}_{prefix}"

    def _create_node(self, node_type, name, tag):
        """Helper para instanciar rápido usando tu NodeCreator."""
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

    def apply_soft_ik(self, ik_ctrl, ik_handle, mid_jnt, root_ctrl, low_jnt, global_ctrl, ik_hdl, root_jnt,
                      goal_ctrl=None):
        """
        Crea las conexiones de nodos para el Soft IK.

        Args:
            ik_ctrl (str): Nombre del control IK (donde está el atributo .Soft).
            ik_handle (str): Nombre del IK Handle a suavizar.
            root_jnt (str): El joint IK inicial de la cadena (Thigh o Shoulder).
            mid_jnt (str): El joint IK intermedio (Knee o Elbow).
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

        # Asegurar que el atributo Soft existe, si no, lo creamos
        if not cmds.attributeQuery("Soft", node=ik_ctrl, exists=True):
            cmds.addAttr(ik_ctrl, ln="Soft", at="double", min=0, max=1, dv=0, k=True)



        # 1. Crear los dos multiplyDivide
        #Saber que el nodo de multiplicación es para multiplicar la longitud de cada hueso por el valor del atributo Soft.
        upperLenghtMult_node = self._create_node("floatMath", "upperLengthMult", "FLM")
        lowerLenghtMult_node = self._create_node("floatMath", "lowerLengthMult", "FLM")
        cmds.setAttr(f"{upperLenghtMult_node}.operation", 2)
        cmds.setAttr(f"{lowerLenghtMult_node}.operation", 2)
        

        # 2. Leer el translateX de cada joint IK y "pegarlo" como valor fijo en Float A
        low_tx = abs(cmds.getAttr(f"{low_jnt}.translateX"))
        mid_tx = abs(cmds.getAttr(f"{mid_jnt}.translateX"))

        cmds.setAttr(f"{upperLenghtMult_node}.floatA", mid_tx)
        cmds.setAttr(f"{lowerLenghtMult_node}.floatA", low_tx)
        
        #Unir los FLM anteriores a un nuevo nodo de Float Math que sume sus resultados y los multiplique por el valor del atributo Soft.
        fullLenght_node = self._create_node("floatMath", "FullLength", "FLM") #queda en dafault pq es Add
        cmds.connectAttr(f"{upperLenghtMult_node}.outFloat", f"{fullLenght_node}.floatA")
        cmds.connectAttr(f"{lowerLenghtMult_node}.outFloat", f"{fullLenght_node}.floatB")
        
        # 4. Distancia REAL entre el Root y el goal (viva, se recalcula siempre)
        # Se mide contra soft_goal_node, que es donde acaba el handle: la
        # distancia tiene que ser la misma que luego recorre el aim, o el soft
        # empieza a actuar a una longitud que no corresponde.
        distance_node = self._create_node("distanceBetween", "rootToIk", "DIST")
        
        cmds.connectAttr(f"{root_ctrl}.worldMatrix[0]", f"{distance_node}.inMatrix1", force=True)
        cmds.connectAttr(f"{soft_goal_node}.worldMatrix[0]",  f"{distance_node}.inMatrix2", force=True)
        
        #5. Float math que divida la distancia total entre el global scale 
        distanceToControlNormalized_node = self._create_node("floatMath", "distanceToControlNormalized", "FLM")
        cmds.setAttr(f"{distanceToControlNormalized_node}.operation", 3) #Divide
        cmds.connectAttr(f"{distance_node}.distance", f"{distanceToControlNormalized_node}.floatA")
        cmds.connectAttr(f"{global_ctrl}.Global_Scale", f"{distanceToControlNormalized_node}.floatB")
        #cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{distanceToControlNormalized_node}.floatB")
        

        
        #Conseguir la diferencia entre full lenght y la initial distance = soft max distance
        outFullLenght_node = self._create_node("floatConstant", "outFullLenght", "FLC")
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{outFullLenght_node}.inFloat")
        
        outDistanceToControlNormalized_node = self._create_node("floatConstant", "outDistanceToControlNormalized", "FLC")
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{outDistanceToControlNormalized_node}.inFloat")
        
        difference_node = self._create_node("floatMath", "difference", "FLM")
        cmds.setAttr(f"{difference_node}.operation", 1) #Subtract
        cmds.connectAttr(f"{outFullLenght_node}.outFloat", f"{difference_node}.floatA")
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{difference_node}.floatB")
        
        differenceValueConstant_node = self._create_node("floatConstant", "differenceValueConstant", "FLC")
        cmds.connectAttr(f"{difference_node}.outFloat", f"{differenceValueConstant_node}.inFloat")
        
        #6. Conectar el soft a un remapValue
        remapValue_node = self._create_node("remapValue", "softValue", "RMV")
        cmds.connectAttr(f"{ik_ctrl}.Soft", f"{remapValue_node}.inputValue")
        cmds.setAttr(f"{remapValue_node}.outputMin",0.001)
        
        #poner el valor de la  diferencia como outMax en el remapValue
        difference_value = cmds.getAttr(f"{differenceValueConstant_node}.outFloat")
        cmds.setAttr(f"{remapValue_node}.outputMax", difference_value)
        
        #7. Soft Max
        
        softDistanceSubstact_node = self._create_node("floatMath", "softDistanceSubstact_node", "FLM")
        cmds.setAttr(f"{softDistanceSubstact_node}.operation", 1) #Substract
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{softDistanceSubstact_node}.floatA")
        cmds.connectAttr(f"{remapValue_node}.outValue", f"{softDistanceSubstact_node}.floatB")
        
        
        #Distance to control minus soft value
        distanceToControl_node = self._create_node("floatMath", "distanceToControlMinusSoftValue", "FLM")
        cmds.setAttr(f"{distanceToControl_node}.operation", 1) #Subtract
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{distanceToControl_node}.floatA")
        cmds.connectAttr(f"{softDistanceSubstact_node}.outFloat", f"{distanceToControl_node}.floatB")

        #8 divide soft distance by soft value
        softExponentDivision_node = self._create_node("floatMath", "softExponentDivision", "FLM")
        cmds.setAttr(f"{softExponentDivision_node}.operation", 3) #Divide
        cmds.connectAttr(f"{distanceToControl_node}.outFloat", f"{softExponentDivision_node}.floatA")
        cmds.connectAttr(f"{remapValue_node}.outValue", f"{softExponentDivision_node}.floatB")
        
        #9 multiply by -1
        softExponentDivisionNegate_node = self._create_node("floatMath", "softExponentDivisionNegate", "FLM")
        cmds.setAttr(f"{softExponentDivisionNegate_node}.operation", 2) #Multiply
        cmds.connectAttr(f"{softExponentDivision_node}.outFloat", f"{softExponentDivisionNegate_node}.floatB")
        cmds.setAttr(f"{softExponentDivisionNegate_node}.floatA", -1)
        
        #10 potencia con el valor de e
        softExponent_node = self._create_node("floatMath", "softExponent", "FLM")
        cmds.setAttr(f"{softExponent_node}.operation", 6) #Power
        cmds.connectAttr(f"{softExponentDivisionNegate_node}.outFloat", f"{softExponent_node}.floatB")
        cmds.setAttr(f"{softExponent_node}.floatA", math.e)
        
        # 11. substract 1 to get the final soft value
        oneMinusSoftExponent_node = self._create_node("floatMath", "oneMinusSoftExponent", "FLM")
        cmds.setAttr(f"{oneMinusSoftExponent_node}.operation", 1) #Subtract
        cmds.connectAttr(f"{softExponent_node}.outFloat", f"{oneMinusSoftExponent_node}.floatB")
        cmds.setAttr(f"{oneMinusSoftExponent_node}.floatA", 1)
        
        #12. Multiply soft distance by the substraction result
        oneMinusSoftExponentBySoftValue_node = self._create_node("floatMath", "oneMinusSoftExponentBySoftValue", "FLM")
        cmds.setAttr(f"{oneMinusSoftExponentBySoftValue_node}.operation", 2) #Multiply
        cmds.connectAttr(f"{remapValue_node}.outValue", f"{oneMinusSoftExponentBySoftValue_node}.floatA")
        cmds.connectAttr(f"{oneMinusSoftExponent_node}.outFloat", f"{oneMinusSoftExponentBySoftValue_node}.floatB")
        
        #13 Soft constant
        softConstantAdd_node = self._create_node("floatMath", "softConstantAdd", "FLM")
        cmds.connectAttr(f"{oneMinusSoftExponentBySoftValue_node}.outFloat", f"{softConstantAdd_node}.floatA")
        cmds.connectAttr(f"{softDistanceSubstact_node}.outFloat", f"{softConstantAdd_node}.floatB")
        
        #14 soft ratio
        softRatio_node = self._create_node("floatMath", "softRatio", "FLM")
        cmds.setAttr(f"{softRatio_node}.operation", 3) #Divide
        cmds.connectAttr(f"{softConstantAdd_node}.outFloat", f"{softRatio_node}.floatA")
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{softRatio_node}.floatB")
        
        #15 length ratio
        lengthRatio_node = self._create_node("floatMath", "lengthRatio", "FLM")
        cmds.setAttr(f"{lengthRatio_node}.operation", 3) #Divide
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{lengthRatio_node}.floatB")
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{lengthRatio_node}.floatA")
        
        #16. distance to control under length ratio
        distanceToControlUnderLengthRatio_node = self._create_node("floatMath", "distanceToControlUnderLengthRatio", "FLM")
        cmds.setAttr(f"{distanceToControlUnderLengthRatio_node}.operation", 3) #Divide
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{distanceToControlUnderLengthRatio_node}.floatA")
        cmds.connectAttr(f"{lengthRatio_node}.outFloat", f"{distanceToControlUnderLengthRatio_node}.floatB")
        
        #17 multiply the two ratios
        softEffectorDistance_node = self._create_node("floatMath", "softEffectorDistanceMult", "FLM")
        cmds.setAttr(f"{softEffectorDistance_node}.operation", 2) #Multiply
        cmds.connectAttr(f"{distanceToControlUnderLengthRatio_node}.outFloat", f"{softEffectorDistance_node}.floatA")
        cmds.connectAttr(f"{softRatio_node}.outFloat", f"{softEffectorDistance_node}.floatB")
        
        #18 Rangos de afectacion del soft
        condition_node = self._create_node("condition", "softCondition", "COND")
        cmds.setAttr(f"{condition_node}.operation", 2) #Greater Than
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{condition_node}.firstTerm")
        cmds.connectAttr(f"{softDistanceSubstact_node}.outFloat", f"{condition_node}.secondTerm")
        cmds.connectAttr(f"{softEffectorDistance_node}.outFloat", f"{condition_node}.colorIfTrueR")
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{condition_node}.colorIfFalseR")

        #crear TRNS y posicionarlos en los joints de la cadena IK con las mismas posiciones y rotaciones, para que el soft IK se aplique a la cadena de joints.
        softOffset_node = cmds.group(empty=True, name=f"{self.prefix}_softOffset_TRN")
        softTransform_node = cmds.group(empty=True, name=f"{self.prefix}_softTransform_TRN")
        cmds.parent(softTransform_node, softOffset_node)
        cmds.matchTransform(softOffset_node, root_jnt, pos=True, rot=True)
        self._parent_into_rig(softOffset_node, soft_parent)

        cmds.pointConstraint(root_ctrl, softOffset_node, mo=False)
        
        # El aim va al soft_goal_node: asi el softTransform viaja sobre la
        # recta root -> destino real del handle, y todo lo que haga el foot
        # roll sigue llegando al tobillo.
        cmds.aimConstraint(soft_goal_node, softOffset_node, mo=False, aimVector=(1, 0, 0), upVector=(0, 1, 0), worldUpType="vector", worldUpVector=(0, 1, 0))
        
        #Conectar el resultado del condition al translateX del softTransform_node
        cmds.connectAttr(f"{condition_node}.outColorR", f"{softTransform_node}.translateX")
        
        #Se elimina el parent constraint entre el ik hdl y el ik ctrl para sustituirlo por este constraint
        cmds.pointConstraint(softTransform_node, ik_hdl, mo=False)
        
        #Cambiamos la tolerancia del ik handle a un valor muy bajo para que el soft IK funcione correctamente(0.00000001)
        cmds.setAttr("ikRPsolver.tolerance", 1e-08)
        
        print(f"[{self.prefix}] Sistema Soft IK conectado centralizadamente.")

        return {
            "softTransform_node": softTransform_node,
            "softGoal_node": soft_goal_node,
            "condition_node": condition_node
        }