"""iPhone-style GUI calculator (Tkinter).

Features:
- Basic arithmetic: +, -, ×, ÷
- Decimals
- Clear (AC/C)
- Toggle sign (±)
- Percent (%)
- Repeat last operation on successive '='
- Keyboard input: 0-9, + - * /, Enter, Esc, Backspace
"""

from __future__ import annotations

import tkinter as tk
from decimal import Decimal, InvalidOperation, getcontext


getcontext().prec = 40


def _decimal_from_text(text: str) -> Decimal:
	# Accept display strings like "0" or "-0.".
	if text in {"", "-", ".", "-.", "0.", "-0."}:
		return Decimal(0)
	try:
		return Decimal(text)
	except InvalidOperation:
		return Decimal(0)


def _format_decimal(value: Decimal) -> str:
	# Avoid scientific notation for typical calculator ranges.
	# Normalize trims trailing zeros but can produce exponent; force fixed-point.
	if value.is_nan():
		return "Error"
	if value == 0:
		return "0"
	sign = "-" if value < 0 else ""
	value = abs(value)

	# Convert to plain string without exponent.
	text = format(value, "f")
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return sign + (text if text else "0")


class RoundedButton(tk.Canvas):
	def __init__(
		self,
		master,
		*,
		text: str,
		command,
		width: int,
		height: int,
		bg: str,
		fg: str,
		activebackground: str | None = None,
		activeforeground: str | None = None,
		font=("Segoe UI", 20),
	) -> None:
		super().__init__(
			master,
			width=width,
			height=height,
			bg="#000000",
			highlightthickness=0,
			bd=0,
		)
		self._text = text
		self._command = command
		self._width = width
		self._height = height
		self._font = font
		self._bg = bg
		self._fg = fg
		self._active_bg = activebackground if activebackground is not None else bg
		self._active_fg = activeforeground if activeforeground is not None else fg
		self._pressed = False

		self.configure(cursor="hand2")
		self._draw()

		self.bind("<ButtonPress-1>", self._on_press)
		self.bind("<ButtonRelease-1>", self._on_release)
		self.bind("<Leave>", self._on_leave)

	def _draw(self) -> None:
		self.delete("all")
		pad = 2
		x0, y0 = pad, pad
		x1, y1 = self._width - pad, self._height - pad
		w = x1 - x0
		h = y1 - y0

		fill = self._active_bg if self._pressed else self._bg
		outline = fill

		# Circle when square-ish, pill when wide.
		if w <= h + 2:
			self.create_oval(x0, y0, x1, y1, fill=fill, outline=outline, tags=("shape",))
		else:
			r = h / 2
			self.create_oval(x0, y0, x0 + 2 * r, y1, fill=fill, outline=outline, tags=("shape",))
			self.create_oval(x1 - 2 * r, y0, x1, y1, fill=fill, outline=outline, tags=("shape",))
			self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline=outline, tags=("shape",))

		fg = self._active_fg if self._pressed else self._fg
		self.create_text(
			self._width / 2,
			self._height / 2,
			text=self._text,
			fill=fg,
			font=self._font,
			tags=("text",),
		)

	def _hit_test(self, x: int, y: int) -> bool:
		return 0 <= x <= self._width and 0 <= y <= self._height

	def _on_press(self, event: tk.Event) -> None:
		self._pressed = True
		self._draw()

	def _on_release(self, event: tk.Event) -> None:
		was_pressed = self._pressed
		self._pressed = False
		self._draw()
		if was_pressed and self._hit_test(int(event.x), int(event.y)):
			self._command()

	def _on_leave(self, _event: tk.Event) -> None:
		if self._pressed:
			self._pressed = False
			self._draw()

	def configure(self, cnf=None, **kw):
		# Support a subset of Button-like options so the rest of the app can
		# update styles/text without knowing this is a Canvas.
		if "text" in kw:
			self._text = kw.pop("text")
		if "bg" in kw:
			self._bg = kw.pop("bg")
		if "fg" in kw:
			self._fg = kw.pop("fg")
		if "activebackground" in kw:
			self._active_bg = kw.pop("activebackground")
		if "activeforeground" in kw:
			self._active_fg = kw.pop("activeforeground")
		result = super().configure(cnf or {}, **kw)
		self._draw()
		return result


class CalculatorApp:
	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("Calculator")
		self.root.configure(bg="#000000")
		self.root.resizable(False, False)

		# State
		self.accumulator = Decimal(0)
		self.current_text = "0"  # what user is typing
		self.pending_op: str | None = None
		self.last_op: str | None = None
		self.last_operand = Decimal(0)
		self.reset_next_entry = False
		self.error_state = False

		# UI
		self.display_var = tk.StringVar(value=self.current_text)
		self._build_ui()
		self._bind_keys()
		self._refresh_clear_label()

	def _build_ui(self) -> None:
		# Display
		display = tk.Label(
			self.root,
			textvariable=self.display_var,
			bg="#000000",
			fg="#FFFFFF",
			anchor="e",
			padx=18,
			pady=18,
			font=("Segoe UI", 36),
		)
		display.grid(row=0, column=0, columnspan=4, sticky="nsew")

		# Colors (approx iOS)
		self.colors = {
			"digit_bg": "#333333",
			"digit_fg": "#FFFFFF",
			"func_bg": "#A5A5A5",
			"func_fg": "#000000",
			"op_bg": "#FF9F0A",
			"op_fg": "#FFFFFF",
			"op_active_bg": "#FFFFFF",
			"op_active_fg": "#FF9F0A",
		}

		# Button layout
		# Each row: (label, kind, command)
		self.clear_button: RoundedButton | None = None
		self.op_buttons: dict[str, RoundedButton] = {}

		layout = [
			[("AC", "func", self.on_clear), ("±", "func", self.on_toggle_sign), ("%", "func", self.on_percent), ("÷", "op", lambda: self.on_operator("/"))],
			[("7", "digit", lambda: self.on_digit("7")), ("8", "digit", lambda: self.on_digit("8")), ("9", "digit", lambda: self.on_digit("9")), ("×", "op", lambda: self.on_operator("*"))],
			[("4", "digit", lambda: self.on_digit("4")), ("5", "digit", lambda: self.on_digit("5")), ("6", "digit", lambda: self.on_digit("6")), ("−", "op", lambda: self.on_operator("-"))],
			[("1", "digit", lambda: self.on_digit("1")), ("2", "digit", lambda: self.on_digit("2")), ("3", "digit", lambda: self.on_digit("3")), ("+", "op", lambda: self.on_operator("+"))],
			[("0", "digit", lambda: self.on_digit("0")), (".", "digit", self.on_decimal), ("=", "op", self.on_equals)],
		]

		# Configure grid weights for consistent sizing
		for c in range(4):
			self.root.grid_columnconfigure(c, minsize=92)
		for r in range(1, 6):
			self.root.grid_rowconfigure(r, minsize=92)

		# Create buttons
		for r, row in enumerate(layout, start=1):
			col = 0
			for (label, kind, cmd) in row:
				if r == 5 and label == "0":
					btn = self._make_button(label, kind, cmd, wide=True)
					btn.grid(row=r, column=col, columnspan=2, sticky="nsew", padx=6, pady=6)
					col += 2
					continue

				btn = self._make_button(label, kind, cmd)
				btn.grid(row=r, column=col, sticky="nsew", padx=6, pady=6)
				col += 1

				if label in {"÷", "×", "−", "+", "="}:
					# Map UI label to internal operator
					if label == "÷":
						self.op_buttons["/"] = btn
					elif label == "×":
						self.op_buttons["*"] = btn
					elif label == "−":
						self.op_buttons["-"] = btn
					elif label == "+":
						self.op_buttons["+"] = btn
					elif label == "=":
						self.op_buttons["="] = btn

				if label == "AC":
					self.clear_button = btn

	def _make_button(self, label: str, kind: str, cmd, *, wide: bool = False) -> RoundedButton:
		if kind == "digit":
			bg = self.colors["digit_bg"]
			fg = self.colors["digit_fg"]
		elif kind == "func":
			bg = self.colors["func_bg"]
			fg = self.colors["func_fg"]
		else:
			bg = self.colors["op_bg"]
			fg = self.colors["op_fg"]

		# Size tuned to look more like iPhone circles/pills.
		height = 84
		width = 84
		if wide:
			width = 84 * 2 + 12
			return RoundedButton(
				self.root,
				text=label,
				command=cmd,
				width=width,
				height=height,
				bg=bg,
				fg=fg,
				activebackground=bg,
				activeforeground=fg,
				font=("Segoe UI", 20),
			)
		return RoundedButton(
			self.root,
			text=label,
			command=cmd,
			width=width,
			height=height,
			bg=bg,
			fg=fg,
			activebackground=bg,
			activeforeground=fg,
			font=("Segoe UI", 20),
		)

	def _bind_keys(self) -> None:
		self.root.bind("<Key>", self._on_key)

	def _on_key(self, event: tk.Event) -> None:
		ch = event.char
		keysym = event.keysym

		if keysym in {"Return", "KP_Enter"}:
			self.on_equals()
			return
		if keysym == "Escape":
			self.on_all_clear()
			return
		if keysym == "BackSpace":
			self.on_backspace()
			return

		if ch.isdigit():
			self.on_digit(ch)
			return
		if ch == ".":
			self.on_decimal()
			return
		if ch in {"+", "-", "*", "/"}:
			self.on_operator(ch)
			return

	def _set_display(self, text: str) -> None:
		self.display_var.set(text)

	def _set_error(self) -> None:
		self.error_state = True
		self.pending_op = None
		self.last_op = None
		self.last_operand = Decimal(0)
		self.reset_next_entry = True
		self._set_display("Error")
		self._update_op_highlight(None)
		self._refresh_clear_label()

	def _refresh_clear_label(self) -> None:
		if not self.clear_button:
			return
		if self.error_state:
			self.clear_button.configure(text="AC")
			return
		# iPhone style: AC when fully reset, C otherwise.
		is_all_clear = (
			self.current_text == "0"
			and self.accumulator == 0
			and self.pending_op is None
			and not self.reset_next_entry
		)
		self.clear_button.configure(text="AC" if is_all_clear else "C")

	def _update_op_highlight(self, op: str | None) -> None:
		for k, btn in self.op_buttons.items():
			if k == "=":
				# Don't highlight '='
				continue
			if op is not None and k == op:
				btn.configure(
					bg=self.colors["op_active_bg"],
					fg=self.colors["op_active_fg"],
					activebackground=self.colors["op_active_bg"],
					activeforeground=self.colors["op_active_fg"],
				)
			else:
				btn.configure(
					bg=self.colors["op_bg"],
					fg=self.colors["op_fg"],
					activebackground=self.colors["op_bg"],
					activeforeground=self.colors["op_fg"],
				)

	def _commit_pending(self, rhs: Decimal) -> None:
		if self.pending_op is None:
			self.accumulator = rhs
			return

		try:
			if self.pending_op == "+":
				self.accumulator = self.accumulator + rhs
			elif self.pending_op == "-":
				self.accumulator = self.accumulator - rhs
			elif self.pending_op == "*":
				self.accumulator = self.accumulator * rhs
			elif self.pending_op == "/":
				if rhs == 0:
					raise ZeroDivisionError
				self.accumulator = self.accumulator / rhs
		except ZeroDivisionError:
			self._set_error()

	def on_digit(self, digit: str) -> None:
		if self.error_state:
			self.on_all_clear()

		if self.reset_next_entry:
			self.current_text = "0"
			self.reset_next_entry = False

		if self.current_text == "0":
			self.current_text = digit
		elif self.current_text == "-0":
			self.current_text = "-" + digit
		else:
			self.current_text += digit

		self._set_display(self.current_text)
		self._refresh_clear_label()

	def on_decimal(self) -> None:
		if self.error_state:
			self.on_all_clear()
		if self.reset_next_entry:
			self.current_text = "0"
			self.reset_next_entry = False
		if "." not in self.current_text:
			self.current_text += "."
		self._set_display(self.current_text)
		self._refresh_clear_label()

	def on_backspace(self) -> None:
		if self.error_state:
			self.on_all_clear()
			return
		if self.reset_next_entry:
			return

		if len(self.current_text) <= 1 or (len(self.current_text) == 2 and self.current_text.startswith("-")):
			self.current_text = "0"
		else:
			self.current_text = self.current_text[:-1]

		self._set_display(self.current_text)
		self._refresh_clear_label()

	def on_operator(self, op: str) -> None:
		if self.error_state:
			return

		if op not in {"+", "-", "*", "/"}:
			return

		rhs = _decimal_from_text(self.current_text)

		# If user presses operator repeatedly, just change pending op.
		if self.pending_op is not None and self.reset_next_entry:
			self.pending_op = op
			self._update_op_highlight(op)
			return

		if self.pending_op is None:
			self.accumulator = rhs
		else:
			self._commit_pending(rhs)
			if self.error_state:
				return

		self.pending_op = op
		self.last_op = None
		self._set_display(_format_decimal(self.accumulator))
		self.current_text = _format_decimal(self.accumulator)
		self.reset_next_entry = True
		self._update_op_highlight(op)
		self._refresh_clear_label()

	def on_equals(self) -> None:
		if self.error_state:
			return

		# If there's a pending op, compute it with current entry.
		if self.pending_op is not None:
			rhs = _decimal_from_text(self.current_text)
			op = self.pending_op
			self._commit_pending(rhs)
			if self.error_state:
				return
			self.last_op = op
			self.last_operand = rhs
			self.pending_op = None
			self._update_op_highlight(None)
		else:
			# Repeat last operation on successive '='
			if self.last_op is not None:
				self.pending_op = self.last_op
				self._commit_pending(self.last_operand)
				self.pending_op = None
				if self.error_state:
					return

		self.current_text = _format_decimal(self.accumulator)
		self._set_display(self.current_text)
		self.reset_next_entry = True
		self._refresh_clear_label()

	def on_percent(self) -> None:
		if self.error_state:
			return
		value = _decimal_from_text(self.current_text)
		value = value / Decimal(100)
		self.current_text = _format_decimal(value)
		self._set_display(self.current_text)
		self._refresh_clear_label()

	def on_toggle_sign(self) -> None:
		if self.error_state:
			return
		if self.current_text.startswith("-"):
			self.current_text = self.current_text[1:]
		else:
			if self.current_text != "0":
				self.current_text = "-" + self.current_text
			else:
				# allow typing a negative number starting from 0
				self.current_text = "-0"

		self._set_display(self.current_text)
		self._refresh_clear_label()

	def on_clear(self) -> None:
		# AC when fully reset, otherwise C.
		if self.error_state:
			self.on_all_clear()
			return

		is_all_clear = (
			self.current_text == "0"
			and self.accumulator == 0
			and self.pending_op is None
			and not self.reset_next_entry
		)
		if is_all_clear:
			self.on_all_clear()
		else:
			self.current_text = "0"
			self._set_display(self.current_text)
			self.reset_next_entry = False
			self._refresh_clear_label()

	def on_all_clear(self) -> None:
		self.accumulator = Decimal(0)
		self.current_text = "0"
		self.pending_op = None
		self.last_op = None
		self.last_operand = Decimal(0)
		self.reset_next_entry = False
		self.error_state = False
		self._update_op_highlight(None)
		self._set_display(self.current_text)
		self._refresh_clear_label()


def main() -> None:
	root = tk.Tk()
	app = CalculatorApp(root)
	root.mainloop()


if __name__ == "__main__":
	main()

