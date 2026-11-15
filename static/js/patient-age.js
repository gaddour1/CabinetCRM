(() => {
  const birthDate = document.getElementById("id_date_of_birth");
  const ageField = document.getElementById("patient-age");

  if (!birthDate || !ageField) {
    return;
  }

  const updateAge = () => {
    const value = birthDate.value;
    if (!value) {
      ageField.value = "";
      return;
    }

    const [year, month, day] = value.split("-").map(Number);
    if (!year || !month || !day) {
      ageField.value = "";
      return;
    }

    const today = new Date();
    ageField.value =
      today.getFullYear() -
      year -
      (today.getMonth() + 1 < month ||
      (today.getMonth() + 1 === month && today.getDate() < day)
        ? 1
        : 0);
  };

  birthDate.addEventListener("input", updateAge);
  birthDate.addEventListener("change", updateAge);
  updateAge();
})();
