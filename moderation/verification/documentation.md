# Verification
This Cog is used to add a Verification System.

## add
With the `add` subcommand you can a Verification Role.
You can set `reverse` to `true` then the Role will get removed from the user and not added.
```css
.verification [add|a|+] <role> [reverse=False]
```
Argument | Required            | Description
---------|---------------------|------------
role     | :heavy_check_mark:  | The Verification Role
reverse  |                     | The Role assignment will be reversed => Role will get removed

Required Permissions:
- `settings.change_prefix`

## delay
Set the Time you have to be on the Server until you can Verify.

```css
.verification [delay|d] <seconds>
```
Argument | Required            | Description
---------|---------------------|------------
delay    | :heavy_check_mark:  | The Time in Seconds

## password
Sets the *Secret* Password you'll need to Verify.
```css
.verification [password|p] <password>
```
Argument | Required            | Description
---------|---------------------|------------
password | :heavy_check_mark:  | The Password as string

!!! note
    Password has a Max-Length of 256 Chars

## remove
Removes an existing Verification.
```css
.verification [remove|r|-] <role>
```
Argument | Required            | Description
---------|---------------------|------------
role     | :heavy_check_mark:  | The Verification Role