Documentation on how to edit the schemata.

In the future the rivm.json, and ui_rivm.json are generated automatically. 
For now some manual changes need to be made, to present the json form in a proper way.

rivm.json:
- Added some explanation for users
- Removed some headers that contained confusing information
- The Bewaartermijn part was unusable, changed parts of this manually.
    - added the url to the description
    - removed old entries with * from dropdown list, they do not match with the Selectielijst

ui_rivm.json, has the same basic structure as the rivm.json.
the ui_rivm.json is used for: 
- hiding fields 
- setting placeholders for dates to jjjj-mm-dd
    - if more than one subfields have a date they need to be wrapped in items: {}
