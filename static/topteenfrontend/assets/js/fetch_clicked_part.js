function fetchCurrentPart(courseName, partId, part_or_quiz, show_part_id) {
    console.log("Fetching current part with parameters");
    if (String(partId) === String(show_part_id)) {
      // console.log("The partId is the same as show_part_id:", partId);
      return; // Exit the function without performing any action
    }
    const url = `/fetch_current_part/${encodeURIComponent(courseName)}/${partId}/${part_or_quiz}/`;
    console.log("Redirecting to URL:", url);
    window.location.href = url;
  }