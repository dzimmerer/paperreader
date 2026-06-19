document.addEventListener("DOMContentLoaded", function () {
  // Scroll to the element with ID "scroll_here" after the page loads
  const scrollToElement = () => {
    const targetElement = document.getElementById("scroll_here");
    const scrollEnabled = localStorage.getItem("scroll-enabled-store");
    // console.log("scroll_enabled", scrollEnabled);
    // console.log("targetElement", targetElement);
    if (scrollEnabled === "true" && targetElement) {
      targetElement.scrollIntoView({ behavior: "smooth", block: "start" });
      console.log("Scrolled to element with ID 'scroll_here'");
    }
  };

  // Listen for page updates triggered by Dash
  const observer = new MutationObserver(scrollToElement);
  const config = { childList: true, subtree: true }; // Observe updates in the DOM

  // Observe the body or a specific container for updates
  const targetNode = document.body;
  if (targetNode) {
    observer.observe(targetNode, config);
  }

  // Scroll initially on page load
  scrollToElement();

  button_ids_list = [
    "button_div_bckwrd",
    "button_div_fwd",
    "button_sent_fwd",
    "button_sent_bckwrd",
  ];

  const observeDOM = () => {
    // Use MutationObserver to watch for changes in the DOM
    const observer = new MutationObserver((mutationsList, observer) => {
      mutationsList.forEach((mutation) => {
        // Check if the button exists and attach the event listener
        for (let i = 0; i < button_ids_list.length; i++) {
          const button = document.getElementById(button_ids_list[i]);
          if (button && !button.dataset.listenerAdded) {
            button.addEventListener("click", function () {
              const targetElement = document.getElementById("scroll_here");
              if (targetElement) {
                targetElement.scrollIntoView({
                  behavior: "smooth",
                  block: "start",
                });
                console.log('Scrolled to element with ID "scroll_here"');
              }
            });
            // Mark the button to avoid adding the listener multiple times
            button.dataset.listenerAdded = true;
          }
        }
      });
    });

    // Start observing the body or a specific container
    const config = { childList: true, subtree: true };
    observer.observe(document.body, config);
  };

  observeDOM(); // Start observing

  // for (let i = 0; i < button_ids_list.length; i++) {
  //   const button = document.getElementById(button_ids_list[i]);
  //   console.log("button", button_ids_list[i], button);
  //   if (button) {
  //     button.addEventListener("click", function () {
  //       console.log("button clicked", button_ids_list[i]);
  //       const targetElement = document.getElementById("scroll_here");
  //       if (targetElement) {
  //         targetElement.scrollIntoView({ behavior: "smooth", block: "start" });
  //         console.log('Scrolled to element with ID "scroll_here"');
  //       }
  //     });
  //   }
  // }
});
