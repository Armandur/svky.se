# The undocumented Swish app link format

`swish://payment?data=<url-encoded JSON>` - what actually works, measured on a
real phone in September 2026.

*Svensk version: [swish-applankens-format.md](#file-swish-applankens-format-md)*

> **Swish does not document this format.** Their developer docs only describe
> `swish://paymentrequest?token=…&callbackurl=…`, which requires a Handel API
> token, certificates and a merchant agreement. The `payment?data=` form below
> is community knowledge. It works today, but nothing guarantees it will keep
> working.

## Why this page exists

Several open source projects build these links, and they disagree on the
details. Two widely copied implementations use string values for `version`. Two
others use numbers. We had a production system running the string form, and it
silently stopped filling in the payment. The app opened to an empty screen.

So we measured. Every table below is an observed result from tapping a link on
a phone with a real Swish number, not a reading of any specification.

## The short answer

```json
{
  "version": 1,
  "payee":   {"value": "1231234567"},
  "amount":  {"value": 149.5},
  "message": {"value": "Invoice 1042"}
}
```

JSON-stringify it, URL-encode the whole string, append to
`swish://payment?data=`.

> **`"version": "1.0"` breaks the link.** The app opens but fills in nothing.
> It must be the *number* `1`. This was the single difference between a working
> link and a dead one.

## Measurement 1: which form fills in the payment

Six forms, same phone, same real Swish number.

| Form | Result |
| --- | --- |
| `version` and `amount` as numbers | Works. Payment view, fields locked |
| same, `payee` as a number too | Works |
| same, plus `"editable": false` everywhere | Works |
| **everything as strings, `"version": "1.0"`** | **App opens, nothing filled in** |
| `version` as number, `amount` as string | Works |
| `payee` only, no amount | Works. App prompts for amount |

`amount` tolerates both a number and a numeric string. `version` does not
tolerate a string.

## Measurement 2: amounts with öre (decimals)

| Value sent | Result |
| --- | --- |
| `"amount": {"value": 1.15}` | Works, shows 1,15 kr |
| `"amount": {"value": "1.15"}` | Works |
| `"amount": {"value": "1,15"}` | **Fails** |

**Decimal point, never a comma**, even though Swedish notation and the QR code
payload both use a comma. The two formats look similar and are not the same,
which is an easy bug to write and a hard one to notice.

## Measurement 3: an open amount (donations)

For a donation where the payer chooses the amount, the working answer is to
**leave the key out entirely**.

| Form | Result |
| --- | --- |
| `"amount": {"value": "", "editable": true}` | Fails |
| `"amount": {"value": ""}` | Fails |
| `"amount": {"value": null, "editable": true}` | Fails |
| **no `amount` key, `message` kept** | **Works. Empty amount field, message intact** |
| no `amount`, `message` editable | Works |
| `"amount": {"value": "0", "editable": true}` | Opens, but forces the payer to change from zero and warns that 1 kr is the minimum |

```json
{
  "version": 1,
  "payee":   {"value": "1231234567"},
  "message": {"value": "Donation"}
}
```

## Measurement 4: the payee cannot be locked

This is the finding with real consequences.

`"editable": true` lets the payer change a field. Omitting the key locks it,
and `"editable": false` is accepted but redundant. That is what you would
expect.

**But as soon as any field carries `editable: true`, the payee number becomes
editable too** - whatever `payee` itself says. Six forms were tested, including
`"editable": false` on `payee` explicitly. None of them kept the number locked.
Only a fully locked link keeps it locked.

| Form | Payee editable? |
| --- | --- |
| Everything locked | No |
| Amount editable, `payee` explicitly `"editable": false` | **Yes** |
| Amount editable, `payee` with no key | **Yes** |
| Message editable, `payee` explicitly locked | **Yes** |
| Amount editable, no `message` key at all | **Yes** |

So an app link with an open amount also lets whoever opens it redirect the
payment to a different number. On a code printed on a poster or an invoice,
that is not a cosmetic issue.

**Correction 2026-09-08: the scanned QR code behaves the same way.** This page
first claimed the QR code's lock mask held where the app link's did not.
It does not. Scanning a code with a locked payee but an open amount lets the
payer change the number too, exactly as the app link does. The lock mask
governs which fields the app pre-fills as editable - it does not pin the
payee. Measured on a phone; the earlier claim was never tested for the QR
path and was carried over by assumption.

What follows from it:

- **Nothing keeps the payee locked except locking every field.** That holds
  for the printed code and the app link alike.
- Whoever creates a code should be told what it allows, for the values they
  entered. Listing the checkboxes is not enough: the payee becomes editable
  without anyone ticking it, and text saying otherwise contradicts reality on
  one point that matters.
- Treat it as **information, not a warning**. The payer can only redirect
  their own payment, sees the payee before signing with BankID, and rarely
  has reason to move a church collection to themselves. For a sale in
  person the seller verifies the payment arrived anyway, in the Swish app
  or on the account - which you do regardless of how the code is locked.
- A fully locked code is safe in both forms.

## Measurement 5: app.swish.nu opens the app, but does not carry the format

The question was whether `swish://` could be replaced by a plain https URL. A
custom URI scheme does nothing at all when the app is missing - no page, no
message - and several apps and webviews refuse to open unknown schemes, so a
link in a mailing can be dead without the sender noticing.

**The domain exists and is genuine.** `app.swish.nu` is registered as a
Universal Link on iOS and an App Link on Android, for `se.bankgirot.swish` -
the production app, not a test build. Retrieved 2026-09-09:

| File | Contents |
| --- | --- |
| `/.well-known/apple-app-site-association` | `appID: 7PQRK67B3Y.se.bankgirot.swish`, `paths: ["/", "*"]` |
| `/.well-known/assetlinks.json` | `package_name: se.bankgirot.swish`, `handle_all_urls` |

Without the app, the domain serves a "Download Swish" page linking to the App
Store and Google Play.

**But it does not carry our format.** Measured on a phone 2026-09-09 across
four paths - `/payment`, `/`, `/1/p/` and `/paymentrequest`, each with the same
`?data=<URL-encoded JSON>` that `swish://` uses:

> Swish opened, but empty. No amount, no message, no payee.

So the Universal Link association works - the app launches - but the `?data=`
payload never reaches it. The domain is no good for a prefilled payment.

**Consequence: `swish://payment?data=` stays.** It is worse at fallback but the
only form that actually fills the fields.

**Still open as an option:** since `app.swish.nu` shows "Download Swish" only
when the app is missing, and opens the app when it is present, it works as a
*supplementary* link for people without Swish - alongside `swish://` for the
payment itself. Not built, and a separate decision.

**What Swish themselves document:** their "Trigger the Swish app" guide on
developer.swish.nu describes only
`swish://paymentrequest?token=<token>&callbackurl=<url>`. That token comes from
the Commerce API and requires a contract and certificates, so it does not apply
here. The format on this page still appears nowhere in Swish's own
documentation - it was derived from the app.

## The QR code payload is a different format

Don't mix them up. The scannable code carries a semicolon-separated string, not
JSON, and it uses a comma for decimals where the app link uses a point.

```
C<payee>;<amount>;<url-encoded message>;<lock mask>

C1237856901;100,00;12229445;0
```

| Field | Notes |
| --- | --- |
| `C` | Mandatory prefix |
| `payee` | Digits only, 10 characters |
| `amount` | Two decimals, decimal **comma**: `100,00` |
| `message` | URL-encoded. The app shows and stores 50 characters, though the API schema allows 70. The tighter limit is the real one |
| lock mask | Decimal bitmask: payee 1, amount 2, message 4. A set bit means *editable*, which is the opposite of what the name suggests. An omitted mask reads as 0, locking everything |

Empty fields stay as empty strings between the semicolons: `C1231234567;;;6`.

### Drawing the code

- Error correction **H**. The Swish logo covers the centre, and a printed code
  collects dirt and wear.
- Logo at **25 %** of the code width, measured against the code *without* the
  quiet zone. Measuring against the whole image makes the symbol 31 % of the
  code, close to what H can absorb.
- **No white plate behind the logo.** Swish's logo file already carries its own
  round white background, and their guidelines forbid adding another one.
- The design in section 5 of the v1.7.2 specification (dot pattern, purple
  gradient, cut corner) is **obsolete**. Swish's own current generator produces
  plain black and white codes with the round logo.

**Scaling the logo has a trap.** PNG files often carry black in the colour
channels where they are fully transparent, because the value is invisible
anyway. LANCZOS interpolates colour and alpha separately, so a plain resize
blends that blackness into the edge pixels and leaves a dark fringe around the
logo. Multiply colour by alpha *before* scaling, then composite by hand:
`under × (1 − alpha) + colour`. A normal alpha-mask paste would count alpha
twice and come out too dark.

## Verify decoding, not rendering

A code that renders beautifully and does not scan is the failure that reaches
print. Decode every generated code in your tests.

OpenCV's `QRCodeDetector` is not reliable enough to be the only judge. We found
it fails on certain H-corrected matrices *even with no logo at all*. Twelve of
fourteen suspect codes failed before any symbol was added.
[zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) read all 472 combinations
without error. Use a second decoder, or you will chase bugs that are not yours.

## Reference implementations, and where they disagree

| Project | `version` | `amount` |
| --- | --- | --- |
| [swish-easy](https://github.com/mast4461/swish-easy) | number | number |
| [ruby_swish_qr](https://github.com/linuscorin/ruby_swish_qr) | number | number |
| Various copies in the wild | string `"1.0"` | string |

The number form is the one that works. If you inherited code using strings, it
may have worked once, as ours did, and it does not now.

---

Measured 2026-09-08 on a physical device with a real Swish number, while
building a QR code generator. Every result above is an observation, not a
citation. Formats can change without notice, since none of this is documented
by Swish.

Sources consulted: [swish-easy](https://github.com/mast4461/swish-easy),
[ruby_swish_qr](https://github.com/linuscorin/ruby_swish_qr),
[Swish developer docs on triggering the app](https://developer.swish.nu/documentation/guides/trigger-the-swish-app),
and the *Guide Swish QR code design specification* v1.7.2 section 6.1.
