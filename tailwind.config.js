/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        "wm-black": "#040308",
        "wm-purple": "#21194f",
        "wm-pink": "#c552df",
        "wm-turquoise": "#24aecb",
        "wm-orange": "#ee6947",
        "wm-orange-alert": "#f77300",
        "wm-orangy-box": "#ffede9",
        "wm-lightblue-box": "#f1efff",
        "wm-bg-form": "#7e6af0",
        "wm-light-purple-text": "#b6aafc",
        "wm-yellow": "#f39629",
        whatsapp: "#2eb82e",
        facebook: "#4966b7",
        twitter: "#55acee",
        instagram: "#c552df",
        taf: "#c552df",
        copyurl: "#c552df",
      },
      screens: {
        "nav-md": "940px",
      },
      gridTemplateColumns: {
        petition: "66% 34%",
      },
      fontFamily: {
        "libre-franklin": ["Libre Franklin", "serif"],
        gilroy: ["Gilroy", "sans-serif"],
      },
    },
  },
  plugins: [],
};
