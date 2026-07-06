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

    def apply_soft_ik(self, ik_ctrl, ik_handle, root_jnt, root_ctrl, mid_jnt, global_ctrl):
        """
        Crea las conexiones de nodos para el Soft IK.

        Args:
            ik_ctrl (str): Nombre del control IK (donde está el atributo .Soft).
            ik_handle (str): Nombre del IK Handle a suavizar.
            root_jnt (str): El joint IK inicial de la cadena (Thigh o Shoulder).
            mid_jnt (str): El joint IK intermedio (Knee o Elbow).

        """
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
        root_tx = cmds.getAttr(f"{root_jnt}.translateX")
        mid_tx = cmds.getAttr(f"{mid_jnt}.translateX")

        cmds.setAttr(f"{upperLenghtMult_node}.floatA", root_tx)
        cmds.setAttr(f"{lowerLenghtMult_node}.floatA", mid_tx)
        
        #Unir los FLM anteriores a un nuevo nodo de Float Math que sume sus resultados y los multiplique por el valor del atributo Soft.
        fullLenght_node = self._create_node("floatMath", "FullLength", "FLM") #queda en dafault pq es Add
        
        cmds.connectAttr(f"{upperLenghtMult_node}.outFloat", f"{fullLenght_node}.floatA")
        cmds.connectAttr(f"{lowerLenghtMult_node}.outFloat", f"{fullLenght_node}.floatB")
        
        # 4. Distancia REAL entre el Root y el Control IK (viva, se recalcula siempre)
        distance_node = self._create_node("distanceBetween", "rootToIk", "DIST")
        
        cmds.connectAttr(f"{root_ctrl}.worldMatrix[0]", f"{distance_node}.inMatrix1", force=True)
        cmds.connectAttr(f"{ik_ctrl}.worldMatrix[0]",  f"{distance_node}.inMatrix2", force=True)
        
        #5. Float math que divida la distancia total entre el global scale 
        distanceToControlNormalized_node = self._create_node("floatMath", "distanceToControlNormalized", "FLM")
        cmds.setAttr(f"{distanceToControlNormalized_node}.operation", 3) #Divide
        cmds.connectAttr(f"{distance_node}.distance", f"{distanceToControlNormalized_node}.floatA")
        cmds.connectAttr(f"{global_ctrl}.Global_Scale", f"{distanceToControlNormalized_node}.floatB")
        #cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{distanceToControlNormalized_node}.floatB")
        
        #6. Conectar el soft a un remapValue
        remapValue_node = self._create_node("remapValue", "softValue", "RMV")
        cmds.connectAttr(f"{ik_ctrl}.Soft", f"{remapValue_node}.inputValue")
        cmds.setAttr(f"{remapValue_node}.outputMin",0.001)
        
        #Conseguir la diferencia entre full lenght y la initial distance = soft max distance
        outFullLenght_node = self._create_node("floatConstant", "outFullLenght", "FLC")
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{outFullLenght_node}.inFloat")
        
        outDistanceToControlNormalized_node = self._create_node("floatConstant", "outDistanceToControlNormalized", "FLC")
        cmds.connectAttr(f"{distanceToControlNormalized_node}.outFloat", f"{outDistanceToControlNormalized_node}.inFloat")
        
        difference_node = self._create_node("floatMath", "difference", "FLM")
        cmds.setAttr(f"{difference_node}.operation", 1) #Subtract
        cmds.connectAttr(f"{outFullLenght_node}.outFloat", f"{difference_node}.floatB")
        cmds.connectAttr(f"{outDistanceToControlNormalized_node}.outFloat", f"{difference_node}.floatA")
        
        #poner el valor de la  diferencia como outMax en el remapValue
        difference_value = cmds.getAttr(f"{difference_node}.outFloat")
        cmds.setAttr(f"{remapValue_node}.outputMax", difference_value)
        
        #7. Soft Max
        
        softDistanceSubstact_node = self._create_node("floatMath", "softDistanceSubstact_node", "FLM")
        cmds.setAttr(f"{softDistanceSubstact_node}.operation", 1) #Substract
        cmds.connectAttr(f"{fullLenght_node}.outFloat", f"{softDistanceSubstact_node}.floatA")
        cmds.connectAttr(f"{remapValue_node}.outValue", f"{softDistanceSubstact_node}.floatB")
        
        
        #Distance to control minus soft value
        distanceToControl_node = self._create_node("floatMath", "distanceToControlMinusSoftValue", "FLM")
        cmds.setAttr(f"{distanceToControl_node}.operation", 1) #Subtract
        cmds.connectAttr(f"{outDistanceToControlNormalized_node}.outFloat", f"{distanceToControl_node}.floatA")
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

        print(f"[{self.prefix}] Sistema Soft IK conectado centralizadamente.")