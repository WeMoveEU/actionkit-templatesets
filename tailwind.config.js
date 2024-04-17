/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./WeMove/*.{html,js}"],
  theme: {
    extend: {
      colors: {
        "wm-black": "#040308",
        "wm-purple": "#21194f",
        "wm-pink": "#c552df",
        "wm-turquoise": "#24aecb",
        "wm-orange": "#ee6947",
        "wm-orangy-box": "#ffede9",
        "wm-lightblue-box": "#f1efff",
        "wm-bg-form": "#7e6af0",
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
