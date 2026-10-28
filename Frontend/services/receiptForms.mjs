// Refresh untouched suggestions while retaining the person's pending edits.
export function syncReceiptForms(forms, receipts) {
 for (const receipt of receipts || []) {
  const amount=String(receipt.amount_fen/100),date=receipt.date || '';
  const previous=forms[receipt.id];
  const amountEdited=!!previous && (previous.amountEdited || previous.amount!==previous.suggestedAmount);
  const dateEdited=!!previous && (previous.dateEdited || previous.date!==previous.suggestedDate);
  forms[receipt.id]={
   amount:amountEdited ? previous.amount : amount,
   date:dateEdited ? previous.date : date,
   suggestedAmount:amount,suggestedDate:date,amountEdited,dateEdited
  };
 }
}
