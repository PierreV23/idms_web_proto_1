// Changes in this file will take effect after running npx webpack.
// Please refer to the README for a guide on how to do this.
import React from 'react';
import { createRoot } from 'react-dom/client';
import Form from "@rjsf/react-bootstrap";
import validator from '@rjsf/validator-ajv8';

// Store roots by element id
const roots = {};
const formRef = React.createRef();

function DescriptionFieldTemplate(props) {
    const { description, id, schema } = props;
    const tooltipText = schema["tooltip"];
    return (
        <div id={id}>
            {description}
            {tooltipText ? (<span tabIndex="0" aria-label={tooltipText} title={tooltipText}><i class="fa-solid fa-circle-info"></i></span>) : null}
        </div>
    );
}

// Not currently used, but could be convenient to have?
window.ValidateRjsfFormData = function () {
    console.log("validating")
    return formRef.current.validateForm()

}

// This function renders the form in the given element.
// It should be available globally so your template JS can call it.
window.renderJsonSchemaForm = function ({ schema, uiSchema, formData, elementId, onChange, onSubmit, onError, formId, afterInitFunction }) {
    const el = document.getElementById(elementId);
    if (!el) return;

    // Create a root if it doesn't exist for this element
    if (!roots[elementId]) {
        roots[elementId] = createRoot(el);
    }

    roots[elementId].render(
        React.createElement(
            Form,
            {
                id: formId,
                schema: schema,
                uiSchema: uiSchema,
                formData: formData,
                onChange: onChange,
                templates: { DescriptionFieldTemplate },
                onSubmit: onSubmit,
                validator: validator,
                onError: onError,
                ref: formRef
            },
            React.createElement("div", null)
        )
    );
    afterInitFunction();
};

window.unmountJsonSchemaForm = function ({ elementId }) {
    console.log("elementId", elementId);
    if (roots.hasOwnProperty(elementId)) {
        roots[elementId].unmount();
        delete roots[elementId];
    }
};