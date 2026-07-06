import maya.cmds as cmds

class NodeCreator(object):
    """
    Classe que crea els nodes amb un naming convention adequat.
    
    Atributs:
        side(str): Afegeix a l'inici del nom la lletra del costat que es el node.
        node_type(str): Tipus de node.
        base_name(str): Nom base pel node.
        name(str): Nom mes especific pel node.
        tag(str): Etiqueta final pel node.
        parent(str): Nom del pare.
        custom_suffix(str): Suffix personalitzat.
    
    """
    def __init__(self, side, node_type, base_name, name, tag, parent, custom_suffix):
        self.side= side
        self.node_type= node_type
        self.base_name= base_name
        self.name= name
        self.tag= tag
        self.parent=parent
        self.custom_suffix= custom_suffix

    def _format_node_name(self):
        """
        
        Construeix el nom base del node.
        
        """
        
        #Crea el nom base sense suffix
        original_name= f"{self.side}_{self.base_name}_{self.name}_{self.tag}"

        #Diccionari amb els nodes i els seus suffixos
        node_suffix = {
        "plusMinusAverage": "PMA",
        "pairBlend": "PBL",
        "multDoubleLinear": "MDL",
        "joint": "JNT",
        "transform": "TRN",
        "multiplyDivide": "MDV",
        "remapValue": "RMV",
        "clamp": "CLP",
        "floatMath": "FLM",
        "reverse": "REV"
        }

        #Si hi ha un suffix personalitzat, li dona prioritat
        if self.custom_suffix:
            suffix= self.custom_suffix

        #Si no hi ha suffix personalitzat i el tipus de node esta dins del diccionari, utilitza el suffix del diccionari
        elif self.node_type in node_suffix: 
            suffix= node_suffix [self.node_type] #POSAR QUE AIXO HE DEMANAT
       
        #Si no es compleix cap de les anteriors, posa un suffix generic.     
        else:
            suffix= "NODE"
        
        return f"{original_name}_{suffix}"
    
    def get_node_name(self):
        """
        
        Genera en el nom un numero incremental, que fa que el nom del node sigui unic.
        
        """
        final_name = self._format_node_name()
        num = 1
       
        #Crea el primer nom amb el suffix numeric
        node_name = f"{final_name}_{str(num).zfill(2)}"
       
        #Si aquest primer nom ja existeix, incrementa el numero
        while cmds.objExists(node_name):
            num += 1
            node_name = f"{final_name}_{str(num).zfill(2)}"
    
        return node_name
        
    def do_parent(self, node_name):
        """
        
        Fa un parent si el node es un dagNode.
        
        """
        
        #Comprova si el node es un dragNode
        if cmds.objectType(node_name, isAType="dagNode"): #Aixo tambe lo del isAType
            
            #Si el pare existeix, deixa fer el parent
            if self.parent and cmds.objExists(self.parent):
                cmds.parent(node_name, self.parent)

    def create(self):
        """
        
        Crea el node amb el nom i fa el parent si es necessari.
        
        """
        
        #Crea el node amb el nom final
        final_node=cmds.createNode(f"{self.node_type}", n=f"{self.get_node_name()}")
       
        #Fa el parent en cas de que n'hi hagui
        self.do_parent(final_node)

        return final_node

#node01= NodeCreator(side="L", node_type="pairBlend", base_name="leg", name="Twist", tag="Upper", parent=None, custom_suffix= None)
#node01.create()