import React from 'react';
import { createRoot } from 'react-dom/client';
import Form from "@rjsf/core";
import validator from '@rjsf/validator-ajv8';

// Store roots by element id
const roots = {};

// This function renders the form in the given element.
// It should be available globally so your template JS can call it.
window.renderJsonSchemaForm = function({schema, uiSchema, formData, elementId, onChange, onSubmit, onError, formId, afterInitFunction}) {
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
                onSubmit: onSubmit,
                validator: validator,
                onError: onError
            },
            React.createElement("div", null)
        ),
        document.getElementById(elementId),
        afterInitFunction()
    );
};

window.unmountJsonSchemaForm = function(elementId) {
  if (elementId in roots){
    roots[elementId].unmount();
  }
};