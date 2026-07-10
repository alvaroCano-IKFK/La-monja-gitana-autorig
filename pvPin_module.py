import maya.cmds as cmds
from nodeCreator_module import NodeCreator
 
 
class Pv_pin(object):
    def __init__(self, side="L", name="leg"):
        self.side = side
        self.name = name
        self.pin_nodes = []
 
    def setup_pole_vector_pin(self, ik_control, root_control, pole_vector_control,
                           soft_trn, soft_condition_node, upper_ik_joint, lower_ik_joint):

        if not cmds.attributeQuery("pin", node=pole_vector_control, exists=True):
            cmds.addAttr(pole_vector_control, ln="pin", at="float", dv=0, min=0, max=1, k=True)

        upper_length_value = cmds.getAttr(f"{upper_ik_joint}.translateX")
        lower_length_value = cmds.getAttr(f"{lower_ik_joint}.translateX")

        dist_root_to_pv_inst = NodeCreator(
            side=self.side, node_type="distanceBetween",
            base_name=self.name, name="rootToPV",
            tag="pin", parent=None, custom_suffix="NOD"
        )
        dist_root_to_pv = dist_root_to_pv_inst.create()

        cmds.connectAttr(f"{root_control}.worldMatrix[0]", f"{dist_root_to_pv}.inMatrix1", force=True)
        cmds.connectAttr(f"{pole_vector_control}.worldMatrix[0]", f"{dist_root_to_pv}.inMatrix2", force=True)

        dist_soft_to_pv_inst = NodeCreator(
            side=self.side, node_type="distanceBetween",
            base_name=self.name, name="softToPV",
            tag="pin", parent=None, custom_suffix="NOD"
        )
        dist_soft_to_pv = dist_soft_to_pv_inst.create()

        cmds.connectAttr(f"{soft_trn}.worldMatrix[0]", f"{dist_soft_to_pv}.inMatrix1", force=True)
        cmds.connectAttr(f"{pole_vector_control}.worldMatrix[0]", f"{dist_soft_to_pv}.inMatrix2", force=True)

        blend_upper_inst = NodeCreator(
            side=self.side, node_type="blendTwoAttr",
            base_name=self.name, name="upperPin",
            tag="segment", parent=None, custom_suffix="NOD"
        )
        blend_upper = blend_upper_inst.create()

        blend_lower_inst = NodeCreator(
            side=self.side, node_type="blendTwoAttr",
            base_name=self.name, name="lowerPin",
            tag="segment", parent=None, custom_suffix="NOD"
        )
        blend_lower = blend_lower_inst.create()

        cmds.connectAttr(f"{pole_vector_control}.pin", f"{blend_upper}.attributesBlender", force=True)
        cmds.connectAttr(f"{pole_vector_control}.pin", f"{blend_lower}.attributesBlender", force=True)

        cmds.setAttr(f"{blend_upper}.input[0]", upper_length_value)
        cmds.setAttr(f"{blend_lower}.input[0]", lower_length_value)

        cmds.connectAttr(f"{dist_root_to_pv}.distance", f"{blend_upper}.input[1]", force=True)
        cmds.connectAttr(f"{dist_soft_to_pv}.distance", f"{blend_lower}.input[1]", force=True)

        cmds.connectAttr(f"{blend_upper}.output", f"{upper_ik_joint}.translateX", force=True)
        cmds.connectAttr(f"{blend_lower}.output", f"{lower_ik_joint}.translateX", force=True)

        self.pin_nodes.extend([dist_root_to_pv, dist_soft_to_pv, blend_upper, blend_lower])

        print(f"[PV Pin] Sistema generat correctament per a: {self.side}_{self.name}")
        return self.pin_nodes