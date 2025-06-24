# Adding a new affiliate: Guide

Since 24.06.2025, the affiliate list is managed through the `affiliates.yaml` file, which is a part of the repository.
So it is much easier to add new affiliates.
`config.yaml` is no longer used for this purpose.

## Steps to add a new affiliate

1. Open `app/data/affiliates.yaml`.
2. Add a new entry in the YAML file with the following structure:

```yaml
affiliates:
  names:
    eld: El Dorito
    t: THORSwap
    tb: TrustWallet
    # new
    new_thorname: New Affiliate Name

  logos:
    shapeshift: fox.png
    vultisig: vult.svg
    asgardex: https://raw.githubusercontent.com/ViewBlock/cryptometa/master/data/thorchain/ecosystem/asgardex/logo.png
    # new
    "New Affiliate Name": new_affiliate_logo.png
```
Note! The `logos` section should contain full names of the affiliates as keys.
Nevertheless, you can ignore the case and spaces.

Logo can be either a local file (e.g., `new_affiliate_logo.png`) or a URL to the image.

3. In case of a local file, make sure to place the image in the `app/data/renderer/static/img/ecosystem` directory.
The optimal image dimensions should be no larger than 400x400 pixels. Please use TinyPNG to compress the image before adding it to the repository. 
