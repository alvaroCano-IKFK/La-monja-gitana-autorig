import maya.cmds as cmds
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

    def apply_soft_ik(self, ik_ctrl, ik_handle, root_jnt, bone1_len, bone2_len):
        """
        Crea las conexiones de nodos para el Soft IK.
        
        Args:
            ik_ctrl (str): Nombre del control IK (donde está el atributo .Soft).
            ik_handle (str): Nombre del IK Handle a suavizar.
            root_jnt (str): El joint inicial de la cadena (Thigh o Shoulder).
            bone1_len (float): Longitud del primer hueso (p.ej. de Thigh a Knee).
            bone2_len (float): Longitud del segundo hueso (p.ej. de Knee a Ankle).
        """
        # Asegurar que el atributo Soft existe, si no, lo creamos
        if not cmds.attributeQuery("Soft", node=ik_ctrl, exists=True):
            cmds.addAttr(ik_ctrl, ln="Soft", at="double", min=0, max=1, dv=0, k=True)

        # Total de la longitud de la cadena estirada (Dmax)
        d_max = bone1_len + bone2_len

        # 1. Medir la distancia real entre el Root y el Control IK
        # Usamos un nodo distanceBetween para calcular la distancia dinámica en tiempo real
        dist_node = self._create_node("distanceBetween", "softIk", "distance")
        
        # Para medir distancias de forma limpia, conectamos las matrices del mundo
        # a través de nodos decomposeMatrix (o directo si usas locator/joints)
        root_decomp = self._create_node("decomposeMatrix", "root", "matrix")
        ctrl_decomp = self._create_node("decomposeMatrix", "ctrl", "matrix")
        
        cmds.connectAttr(f"{root_jnt}.worldMatrix[0]", f"{root_decomp}.inputMatrix")
        cmds.connectAttr(f"{ik_ctrl}.worldMatrix[0]", f"{ctrl_decomp}.inputMatrix")
        
        cmds.connectAttr(f"{root_decomp}.outputTranslate", f"{dist_node}.point1")
        cmds.connectAttr(f"{ctrl_decomp}.outputTranslate", f"{dist_node}.point2")

        # --- RED DE NODOS MATEMÁTICOS PARA SOFT IK ---
        # Formula básica: Si Distancia > (Dmax - Soft), aplicar descompresión exponencial.
        
        # Nodo para pasar el valor estático Dmax a la red
        pma_calc = self._create_node("plusMinusAverage", "softIk", "math")
        
        # Aquí crearías toda tu lógica matemática (Multiplicaciones, potencias o condicionales).
        # Como el Soft IK puramente matemático por nodos puede volverse una "telaraña" enorme,
        # una alternativa muy limpia y usada en la industria es usar una Expression Node temporalmente:
        
        expr_name = f"{self.prefix}_softIK_EXPR"
        
        # Creamos la expresión de Maya que lee del distanceBetween y escribe en el IK Handle
        # NOTA: Ajusta la fórmula a la variación matemática exacta que prefieras.
        expression_string = (
            f"float $d = {dist_node}.distance;\n"
            f"float $da = {d_max};\n"
            f"float $s = {ik_ctrl}.Soft;\n"
            f"if ($s > 0.001) {{\n"
            f"    float $ds = $da - $s;\n"
            f"    if ($d > $ds) {{\n"
            f"        {ik_handle}.translateX = $ds + $s * (1 - exp(-($d - $ds) / $s));\n"
            f"    }} else {{\n"
            f"        {ik_handle}.translateX = $d;\n"
            f"    }}\n"
            f"}} else {{\n"
            f"    {ik_handle}.translateX = $d;\n"
            f"}}"
        )
        
        # Nota: La fórmula asume que el IK Handle se mueve en un eje local estirado. 
        # Si tu IK Handle está metido en grupos intermedios, aplicas el output a la traslación de ese grupo.
        
        cmds.expression(n=expr_name, s=expression_string, cat=True)
        print(f"[{self.prefix}] Sistema Soft IK conectado centralizadamente.")