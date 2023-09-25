// Insanely simple fake encapsulation. =) Meaningless change.
const WeMoveStripe = {
  enableCheckout: (buttonName) => {
    if (buttonName == undefined) {
      buttonName = 'button.stripe-checkout';
    }

    $(() => {
      $('button.stripe-checkout').on('click',
        (e) => {
          const method = $(e.target).data('paymentmethod');

          const path = actionkit.form.donation_type === 'recurring'
            ? 'https://actionkit-stripe-api.not-a2.eu/checkout/subscribe'
            : 'https://actionkit-stripe-api.not-a2.eu/checkout/payment';

          const parsedDate = JSON.stringify({
            "amount": actionkit.form.amount.value,
            "email": actionkit.form.email.value,
            "name": actionkit.form.name.value,
            "line1": actionkit.form.address1.value,
            "line2": actionkit.form.address2.value,
            "postal": actionkit.form.postal.value,
            "city": actionkit.form.city.value,
            "region": actionkit.form.region.value,
            "country": $('#id_country').val(),
            "methods": [method],
          });

          $.post({
            url: path,
            data: parsedDate,
          }).then((response) => {
            window.location = response.url;
          });
        }
      );
    });
  },
  loadElements: (element) => {},
}
