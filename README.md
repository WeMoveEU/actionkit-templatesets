# WeMove ActionKit TemplateSet

There are lots of [docs on template sets](https://docs.actionkit.com/docs/manual/developer/templates_index.html). This document should summarize specifics of our changes.

# Donations

The donate.html template has changes to use Stripe to collect and process payments. The JS and backend code is in [actionkit-stripe-integration](https://gitlab.wemove.eu/internal/actionkit-stripe-integration/) repository.

Short version:

- The actionkit donation form is mostly unchanged - amounts, contact fields and the stepper are all the built in versions.
- The payment step uses our customized Stripe code to load the payment forms and process them. There are calls to initialization functions to load the forms and event handlers to process.
- The template needs to load styles and JS from the [actionkit stripe integration](https://gitlab.wemove.eu/internal/actionkit-stripe-integration/). There are custom classes (which should all be prefixed with wemove- but probably aren't) and ids in the DOM. The wrapper.html template has a wemove class to make it easier to apply styles without changing the default html.

# Developing

There are a few tools in ActionKit that make developing template sets easier. Here's what I've found to be the most effective.

- [Github integration](https://docs.actionkit.com/docs/manual/developer/githubconnection.html) with one branch as production and one branch as main.

- Push changes to the production branch to deploy.

- Use the Link Local Files feature (uses the File API in the browser) to edit locally. On the view of a templateset which lists all the files, there's button to connect your local files to the browser.

      "Live Link Local Files"

      Select files on your computer to be uploaded every time you save changes

- Choose a page to preview using the Select, ActionKit will automatically reload the preview page when it uploads a changed file.

- Save your changes to GitHub on the preview branch often, ActionKit's revert feature is nowhere near as good as Git.

- Merge to the production branch and push.

See the [actionkit stripe integration](https://gitlab.wemove.eu/internal/actionkit-stripe-integration/) for setting up the development environment for this work.

## Local assets proxy

To develop CSS and JS, use the ssh://git@gitlab.wemove.eu:2222/internal/pubstatic.git repository and run the local server (yarn run dev).

If you pass dev=1 to a page, it will use the following URLs to load the assets:

    //127.0.0.1:8081/js/wemove-main.bundle.min.js
    //127.0.0.1:8081/css/wemove.css

# TODOs

## Remove kruft from the donate.html template - there's a lot of code we can remove. Totally worth it.

## The currency switcher needs more work, specifically to match currencies to payment methods. For example you can't use SEPA for GBP or Blik with EURs.

Currency switching requires:

- a form input to let users change and to read the currency
- a way to match payment methods to currency. for example, GBP and SEPA are incompatible
- display updates for amounts
  - update the currency symbol / display
  - update the amounts where needed b/c the currency exchange rates are significantly different

We shouldn't use the ActionKit currency switcher - it does all kinds of weird stuff to handle multiple Braintree accounts (each with a different currency). Stripe just needs an parameter to process the donation in a different currency.

## Translations in donate.html _and_ \*.js files here

If possible it would be good to avoid translations in the JS files, and
to keep it all in ActionKit. Using multiple divs in donate.html instead of inserting
text from the JS?

## Avoid the "Loading" delay on the payment step (3)

To avoid the delay when loading the payment element, we could create a payment intent after the amount is selected, load the form in the background, create the customer when the user details are entered, and update the payment intent to attach it to the customer. I think it's less complicated than it sounds - but not sure. If the load is fast enough in production, meh.

## Mobile version

Two parts here - better responsive styling, a static "Donate Now" banner at the bottom of the page on very small screens.

## Elements version of the UI

This code supports using Checkout and Payment Elements (embedded checkout basically). There should probably be support for Elements too. All of these UIs can rely on the same Webhook code to capture payments. Both elements and payment element use the same basic backend code: 1. get a secret 2. capture payment with secret.
