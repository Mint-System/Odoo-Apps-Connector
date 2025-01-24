/** @odoo-module **/
import {DropdownItem} from "@web/core/dropdown/dropdown_item";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
const {Component} = owl;
const cogMenuRegistry = registry.category("cogMenu");
export class CogMenu extends Component {
    setup() {
        this.orm = useService("orm");
    }
    async actionNewOption() {
        var currentModel = this.env.searchModel.resModel;
        console.log(currentModel);
        const values = this.orm.call(currentModel, "sync_db", []);
    }
}
CogMenu.template = "kardex_cog_menu.SyncOption";
CogMenu.components = {DropdownItem};
export const CogMenuItem = {
    Component: CogMenu,
    groupNumber: 20,
    isDisplayed: ({config}) => config.viewType != "form",
};
cogMenuRegistry.add("new-option", CogMenuItem, {sequence: 10});
