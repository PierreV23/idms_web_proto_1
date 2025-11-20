// metaedit.js
(() => {
  const Form = JSONSchemaForm.default;

  // Render JSON Schema form into a target div
  window.renderFormFunction = function(schema, uiSchema, formData, targetId) {
    const element = React.createElement(Form, {
      schema,
      uiSchema,
      formData,
      onChange: (e) => console.log("changed", e.formData),
      onSubmit: (e) => console.log("submitted", e.formData),
      onError: (e) => console.log("errors", e),
    });

    ReactDOM.render(element, document.getElementById(targetId));
  };

  // Load schema + data + render form
  window.loadSchemaProject = function (schemapath, collection) {
    console.log("Load schema", schemapath);

    $.ajax({
      method: "GET",
      url: window.URLS.metaedit_get_schema_and_data,
      data: {
        schemapath,
        collection,
      },
      dataType: "json",
    })
      .done((result) => {
        console.log("Result", result);

        renderFormFunction(
          JSON.parse(result.schema),
          JSON.parse(result.uiSchema),
          JSON.parse(result.data),
          "reactform"
        );
      })
      .fail((xhr, status, error) => console.error("Schema load failed", status, error));
  };

  // Add/remove schema from collection
  window.toggleRowProject = function (collection, schemapath, action) {
    console.log("TOGGLE", collection, schemapath, action);

    $.ajax({
      method: "POST",
      url: window.URLS.metaedit_set_schemata_for_collection,
      contentType: "application/json; charset=utf-8",
      data: JSON.stringify({
        collection,
        schemapath,
        action,
      }),
      dataType: "json",
    })
      .done((response) => console.log("Schema updated:", response))
      .fail((xhr, status, error) =>
        console.error("Schema update failed:", status, error)
      );
  };
})();
