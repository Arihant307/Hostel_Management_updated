import { useEffect, useState } from 'react';
import Modal from '../../components/ui/Modal.jsx';
import Button from '../../components/ui/Button.jsx';
import Input, { Select } from '../../components/ui/Input.jsx';
import Textarea from '../../components/ui/Textarea.jsx';
import { FormError } from '../../components/ui/Misc.jsx';
import useForm from '../../hooks/useForm.js';
import { allocationService } from '../../services/resources.js';
import { formatMoney, todayISO } from '../../utils/format.js';
import { label } from '../../components/StatusBadge.jsx';

export function TransferModal({ allocation, onClose, onDone }) {
  const form = useForm({ room_id: '', transfer_date: todayISO(), notes: '' });
  const [rooms, setRooms] = useState(null);

  useEffect(() => {
    if (!allocation) return;
    form.reset({ room_id: '', transfer_date: todayISO(), notes: '' });
    setRooms(null);
    allocationService.eligibleRooms({ per_page: 100 })
      .then((d) => setRooms(d.items.filter((r) => r.id !== allocation.room.id)))
      .catch(() => setRooms([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allocation]);

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(
      (v) => allocationService.transfer(allocation.id, {
        room_id: Number(v.room_id), transfer_date: v.transfer_date, notes: v.notes.trim() || null,
      }),
      { validate: (v) => ({ room_id: !v.room_id && 'Choose the new room.' }) },
    );
    if (result) onDone(result);
  };

  return (
    <Modal
      open={Boolean(allocation)}
      onClose={form.submitting ? undefined : onClose}
      title="Transfer student"
      description={allocation ? `${allocation.student.full_name} is currently in room ${allocation.room.block}-${allocation.room.room_number}. The current stay is closed and kept in history.` : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
          <Button type="submit" form="transfer-form" loading={form.submitting}>Transfer</Button>
        </>
      }
    >
      <form id="transfer-form" onSubmit={save} className="space-y-4" noValidate>
        <FormError message={form.formError} />
        <Select label="New room" required {...form.bind('room_id')} disabled={!rooms}
          hint={rooms && rooms.length === 0 ? 'No other room has a free bed.' : undefined}>
          <option value="">{rooms ? 'Select a room with a free bed' : 'Loading rooms…'}</option>
          {rooms?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.block}-{r.room_number} · {label(r.room_type)} · {r.available_beds} free · {formatMoney(r.monthly_fee_minor)}/mo
            </option>
          ))}
        </Select>
        <Input label="Transfer date" type="date" required {...form.bind('transfer_date')} min={allocation?.allocated_on} />
        <Textarea label="Reason / notes" rows={3} {...form.bind('notes')} />
      </form>
    </Modal>
  );
}

export function CheckoutModal({ allocation, onClose, onDone }) {
  const form = useForm({ checkout_date: todayISO(), notes: '' });

  useEffect(() => {
    if (allocation) form.reset({ checkout_date: todayISO(), notes: '' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allocation]);

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit((v) => allocationService.checkout(allocation.id, {
      checkout_date: v.checkout_date, notes: v.notes.trim() || null,
    }));
    if (result) onDone(result);
  };

  return (
    <Modal
      open={Boolean(allocation)}
      onClose={form.submitting ? undefined : onClose}
      title="Check out student"
      description={allocation ? `${allocation.student.full_name} will leave room ${allocation.room.block}-${allocation.room.room_number} and the bed becomes available.` : undefined}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
          <Button variant="danger" type="submit" form="checkout-form" loading={form.submitting}>Check out</Button>
        </>
      }
    >
      <form id="checkout-form" onSubmit={save} className="space-y-4" noValidate>
        <FormError message={form.formError} />
        <Input label="Checkout date" type="date" required {...form.bind('checkout_date')} min={allocation?.allocated_on} />
        <Textarea label="Notes" rows={3} {...form.bind('notes')} placeholder="Room inspected, keys returned…" />
      </form>
    </Modal>
  );
}
