import maya.cmds as cmds
import guides_module
import spine_module
import hip_module
import body_module
import limbs_module
import leg_module


class SpaceModule(object):
    """
    Módulo para la creación de Space Switching (Dynamic Parent) en componentes del Rig.
    Utiliza el grupo intermedio '_SPC' generado por groups_module.py para inyectar las restricciones.
    """

    def __init__(self, target_control, space_dict, attr_name="Space", rig_name="Character"):
        """
        Args:
            target_control (str): El control animable que recibirá el atributo de cambio (ej: 'L_Character_armIk_CTRL').
            space_dict (dict): Diccionario {Nombre_Atributo: Objeto_Target_Rig}
                               Ej: {"Mundo": "Character_local_CTL", "Pecho": "Character_chestFix_CTL"}
            attr_name (str): Nombre del atributo enum que se creará en el control.
            rig_name (str): Nombre del proyecto/personaje para nomenclaturas de nodos.
        """
        self.target_control = target_control
        self.space_dict = space_dict
        self.attr_name = attr_name
        self.rig_name = rig_name
        
        # Encontramos el grupo _SPC correspondiente a este control específico
        self.space_group = self._find_space_group()

    def _find_space_group(self):
        """
        Busca el grupo '_SPC' en la jerarquía superior del control basándose 
        en la nomenclatura estándar de groups_module.py.
        """
        # Reemplazamos los sufijos comunes para dar con el nombre base del control
        base_name = self.target_control
        for suffix in ["_CTRL", "_CTL"]:
            if base_name.endswith(suffix):
                base_name = base_name.rsplit(suffix, 1)[0]
                break

        expected_spc = f"{base_name}_SPC"

        # Validamos si el grupo SPC existe en la escena
        if cmds.objExists(expected_spc):
            return expected_spc
        
        # En caso de que falle por nomenclatura, lo buscamos subiendo por su jerarquía de padres
        current = self.target_control
        while True:
            parent = cmds.listRelatives(current, parent=True)
            if not parent:
                break
            current = parent[0]
            if current.endswith("_SPC"):
                return current
                
        cmds.error(f"[Spaces] No se pudo encontrar el grupo de espacio '_SPC' para el control {self.target_control}.")
        return None

    def build(self):
        """Ejecuta la construcción del sistema de espacios sobre el grupo _SPC."""
        if not cmds.objExists(self.target_control):
            cmds.warning(f"[Spaces] No existe el control objetivo: {self.target_control}. Abortando space setup.")
            return

        if not self.space_group:
            return

        # 1. Crear la lista para el Atributo Enum
        enum_names = ":".join(self.space_dict.keys())
        
        # Añadir un separador visual estético en el Channel Box si no existe
        if not cmds.attributeQuery("spacesSep", node=self.target_control, exists=True):
            cmds.addAttr(self.target_control, ln="spacesSep", nn="SPACES", at="enum", en="------", k=False)
            cmds.setAttr(f"{self.target_control}.spacesSep", cb=True, l=True)

        # Crear el atributo enum controlador del cambio de espacio
        if not cmds.attributeQuery(self.attr_name, node=self.target_control, exists=True):
            cmds.addAttr(self.target_control, ln=self.attr_name, at="enum", en=enum_names, k=True)

        # 2. Configurar los Targets de la Restricción
        targets = list(self.space_dict.values())
        
        # Validar que todos los targets existan en la escena
        valid_targets = [t for t in targets if cmds.objExists(t)]
        if len(valid_targets) != len(targets):
            missing = set(targets) - set(valid_targets)
            cmds.error(f"[Spaces] Faltan los siguientes targets en la escena para configurar el espacio: {missing}")

        # Aplicamos el parentConstraint sobre el grupo '_SPC' manteniendo el offset actual (mo=True)
        constraint = cmds.parentConstraint(valid_targets, self.space_group, mo=True, n=f"{self.space_group}_PRC")[0]
        
        # Obtener la lista de los atributos de peso (weight) generados de manera nativa por el constraint
        weight_aliases = cmds.parentConstraint(constraint, q=True, wal=True)

        # 3. Conectar el Enum a los Pesos del Constraint usando nodos Condition nativos
        for index, space_title in enumerate(self.space_dict.keys()):
            # Creamos un nodo condition por cada espacio objetivo
            cond_node = cmds.createNode("condition", n=f"{self.space_group}_{space_title}_COND")
            
            # Configuración de la condición: Si Enum == Index -> Peso es 1.0 (True), sino es 0.0 (False)
            cmds.setAttr(f"{cond_node}.operation", 0)  # 0 es la operación "Equal"
            cmds.setAttr(f"{cond_node}.secondTerm", index)
            cmds.setAttr(f"{cond_node}.colorIfTrueR", 1.0)
            cmds.setAttr(f"{cond_node}.colorIfFalseR", 0.0)

            # Conectar el atributo enum del control al nodo de condición
            cmds.connectAttr(f"{self.target_control}.{self.attr_name}", f"{cond_node}.firstTerm")
            
            # Conectar el output del condition al canal de peso alias del parentConstraint
            cmds.connectAttr(f"{cond_node}.outColorR", f"{constraint}.{weight_aliases[index]}")

        print(f"[Spaces] Cambiador de espacio conectado con éxito en el grupo intermedio: {self.space_group}")