import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import flet as ft
import flet_audio as fta
import random
import os
import json
import asyncio
import websockets

TAMANIO_TABLERO = 10
MAX_BARCOS = 8

# Tamaño de cada celda y espacio entre ellas
CELDA = 24
ESPACIO = 2
PASO = CELDA + ESPACIO          # 26 px por celda+espacio
TABLERO_PX = TAMANIO_TABLERO * PASO  # 260 px total

def main(page: ft.Page):
    page.title = "Guerra Naval Estratégica"
    page.bgcolor = ft.Colors.BLUE_GREY_900
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # --------------------------------------------------
    # MÚSICA DE FONDO
    # --------------------------------------------------
    musica = fta.Audio(src="musica.mp3", autoplay=True, volume=0.3)
    page.services.append(musica)

    # --------------------------------------------------
    # ESTADO INTERNO DEL JUEGO
    # --------------------------------------------------
    mi_id = str(random.randint(1000, 9999))

    fase_actual = "CONEXION"
    rival_listo = False
    soy_creador = False   # True = creó la sala (empieza atacando primero)
    mi_turno = False      # True = puedo atacar ahora

    mis_barcos_totales = 0
    barcos_totales_enemigo = 0
    barcos_colocados = 0

    mi_mapa = [[0]*TAMANIO_TABLERO for _ in range(TAMANIO_TABLERO)]
    mapa_enemigo = [[0]*TAMANIO_TABLERO for _ in range(TAMANIO_TABLERO)]

    mis_barcos_info = []

    # Stacks para los dos tableros (posicionamiento absoluto)
    mi_stack = ft.Stack(width=TABLERO_PX, height=TABLERO_PX, clip_behavior=ft.ClipBehavior.HARD_EDGE)
    enemigo_stack = ft.Stack(width=TABLERO_PX, height=TABLERO_PX, clip_behavior=ft.ClipBehavior.HARD_EDGE)

    barco_seleccionado = 1
    orientacion = "H"

    IMAGENES_BARCOS = {
        1: "barco1.png",
        2: "barco2.png",
        3: "barco3.png",
        4: "barco4.png",
    }

    def imagen_existe(nombre):
        return os.path.exists(os.path.join("assets", nombre)) or os.path.exists(nombre)

    # --------------------------------------------------
    # LÓGICA DE BARCOS
    # --------------------------------------------------
    def colocar_barco(fila, columna, tamaño, ori):
        nonlocal barcos_colocados
        if barcos_colocados >= MAX_BARCOS:
            return False
        if ori == "H":
            if columna + tamaño > TAMANIO_TABLERO:
                return False
            for c in range(columna, columna + tamaño):
                if mi_mapa[fila][c] != 0:
                    return False
            for c in range(columna, columna + tamaño):
                mi_mapa[fila][c] = tamaño
        else:
            if fila + tamaño > TAMANIO_TABLERO:
                return False
            for f in range(fila, fila + tamaño):
                if mi_mapa[f][columna] != 0:
                    return False
            for f in range(fila, fila + tamaño):
                mi_mapa[f][columna] = tamaño
        mis_barcos_info.append({"fila": fila, "columna": columna, "tamaño": tamaño, "orientacion": ori})
        barcos_colocados += 1
        actualizar_contador()
        return True

    def eliminar_barco(fila, columna):
        nonlocal barcos_colocados
        if mi_mapa[fila][columna] == 0:
            return False
        tamaño = mi_mapa[fila][columna]
        for i, barco in enumerate(mis_barcos_info):
            if barco["tamaño"] == tamaño:
                ori = barco["orientacion"]
                bf, bc = barco["fila"], barco["columna"]
                if ori == "H" and bf == fila and bc <= columna < bc + tamaño:
                    for c in range(bc, bc + tamaño):
                        mi_mapa[fila][c] = 0
                    mis_barcos_info.pop(i)
                    barcos_colocados -= 1
                    actualizar_contador()
                    return True
                elif ori == "V" and bc == columna and bf <= fila < bf + tamaño:
                    for f in range(bf, bf + tamaño):
                        mi_mapa[f][columna] = 0
                    mis_barcos_info.pop(i)
                    barcos_colocados -= 1
                    actualizar_contador()
                    return True
        return False

    def obtener_barco_en(fila, columna):
        """Encuentra cuál de mis barcos ocupa esa celda (o None)."""
        for barco in mis_barcos_info:
            ori = barco["orientacion"]
            bf, bc, tam = barco["fila"], barco["columna"], barco["tamaño"]
            if ori == "H" and bf == fila and bc <= columna < bc + tam:
                return barco
            if ori == "V" and bc == columna and bf <= fila < bf + tam:
                return barco
        return None

    def barco_esta_hundido(barco):
        """True si TODAS las celdas de ese barco ya fueron tocadas (valor 3)."""
        ori = barco["orientacion"]
        bf, bc, tam = barco["fila"], barco["columna"], barco["tamaño"]
        if ori == "H":
            return all(mi_mapa[bf][c] == 3 for c in range(bc, bc + tam))
        return all(mi_mapa[f][bc] == 3 for f in range(bf, bf + tam))

    def actualizar_contador():
        contador_text.value = f"🚢 Barcos: {barcos_colocados}/{MAX_BARCOS}"
        page.update()

    # --------------------------------------------------
    # EVENTOS DE CLIC
    # --------------------------------------------------
    def mi_casilla_click(e):
        nonlocal fase_actual
        if fase_actual != "COLOCACION":
            return
        f, c = e.control.data
        if mi_mapa[f][c] != 0:
            if eliminar_barco(f, c):
                txt_estado.value = f"Barco eliminado. Restantes: {MAX_BARCOS - barcos_colocados}"
                actualizar_pantalla()
            return
        if colocar_barco(f, c, barco_seleccionado, orientacion):
            txt_estado.value = f"✅ Barco de {barco_seleccionado} celda(s) colocado. Restantes: {MAX_BARCOS - barcos_colocados}"
        else:
            if barcos_colocados >= MAX_BARCOS:
                txt_estado.value = f"⚠️ ¡Límite de {MAX_BARCOS} barcos alcanzado!"
            else:
                txt_estado.value = "❌ No se puede colocar el barco ahí."
        actualizar_pantalla()

    def seleccionar_barco(tamaño):
        def on_click(e):
            nonlocal barco_seleccionado
            barco_seleccionado = tamaño
            txt_estado.value = f"🛳️ Barco de {tamaño} celda(s) seleccionado."
            for btn in botones_barcos:
                btn.bgcolor = ft.Colors.GREY_800
            botones_barcos[tamaño - 1].bgcolor = ft.Colors.GREEN_800
            page.update()
        return on_click

    def cambiar_orientacion(e):
        nonlocal orientacion
        orientacion = "V" if orientacion == "H" else "H"
        btn_orientacion.content = ft.Text(
            "↕ VERTICAL" if orientacion == "V" else "↔ HORIZONTAL",
            size=11, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD
        )
        txt_estado.value = f"Orientación: {'Vertical' if orientacion == 'V' else 'Horizontal'}"
        page.update()

    # --------------------------------------------------
    # 🌐 RED / MULTIJUGADOR (WebSocket a servidor propio, por código de sala)
    # --------------------------------------------------
    # ⚠️ Cambia esto por la URL real de tu servidor una vez que lo despliegues
    # en Render (o el hosting que uses). Con Render queda algo así, SIN
    # número de puerto al final (Render lo maneja solo detrás de HTTPS):
    #   DIRECCION_SERVIDOR = "wss://guerra-naval-xxxx.onrender.com"
    DIRECCION_SERVIDOR = "wss://guerra-naval-server.onrender.com"

    conexion = {"socket": None}

    def recibir_mensaje_red(mensaje_red):
        nonlocal rival_listo, fase_actual, barcos_totales_enemigo, mi_turno
        tipo = mensaje_red.get("tipo")

        if tipo == "listo":
            rival_listo = True
            barcos_totales_enemigo = mensaje_red.get("cantidad_barcos", 0)
            if fase_actual == "ESPERANDO_RIVAL":
                fase_actual = "BATALLA"
                mi_turno = soy_creador
                txt_estado.value = "🎯 ¡Tu turno! Ataca el radar enemigo." if mi_turno else "⏳ El enemigo ataca primero. Espera tu turno..."
            else:
                txt_estado.value = "El rival ya colocó sus barcos. ¡Apresúrate!"
            page.update()

        elif tipo == "ataque" and fase_actual == "BATALLA":
            f, c = mensaje_red["fila"], mensaje_red["columna"]
            resultado = "tocado" if mi_mapa[f][c] >= 1 else "agua"
            mi_mapa[f][c] = 3 if resultado == "tocado" else 2
            mi_turno = True  # el rival ya disparó, ahora te toca a ti
            hundido = False
            if resultado == "tocado":
                barco = obtener_barco_en(f, c)
                if barco and barco_esta_hundido(barco):
                    hundido = True
            actualizar_pantalla()
            if not verificar_fin_del_juego():
                if hundido:
                    txt_estado.value = "💀🚢 ¡Te hundieron un barco entero! Tu turno."
                else:
                    txt_estado.value = "🎯 ¡Tu turno! " + ("¡Te dieron! 💥" if resultado == "tocado" else "El rival falló. 🌊")
                page.update()
            enviar_red({"tipo": "respuesta", "fila": f, "columna": c, "resultado": resultado, "hundido": hundido})

        elif tipo == "respuesta" and fase_actual == "BATALLA":
            f, c = mensaje_red["fila"], mensaje_red["columna"]
            res = mensaje_red["resultado"]
            hundido = mensaje_red.get("hundido", False)
            mapa_enemigo[f][c] = 3 if res == "tocado" else 2
            actualizar_pantalla()
            if not verificar_fin_del_juego():
                if hundido:
                    txt_estado.value = "💥🚢 ¡PUM! Hundiste un barco entero. Turno del rival. ⏳"
                else:
                    impacto = "¡Impacto! 🔥" if res == "tocado" else "🌊 Al agua."
                    txt_estado.value = f"{impacto} Ahora es turno del rival. ⏳"
                page.update()

    def enviar_red(mensaje):
        """Manda un mensaje del juego (ataque, respuesta, listo...) al rival,
        a través del servidor, que lo reenvía a la otra persona en la sala."""
        socket_actual = conexion["socket"]
        if not socket_actual:
            return
        async def _enviar():
            try:
                await socket_actual.send(json.dumps({"accion": "reenviar", "payload": mensaje}))
            except Exception:
                pass
        page.run_task(_enviar)

    async def _escuchar_servidor(socket_actual):
        """Tarea de fondo: se queda escuchando mensajes del servidor mientras
        dure la conexión (tanto del emparejamiento como del juego en sí)."""
        try:
            async for mensaje in socket_actual:
                datos = json.loads(mensaje)
                _procesar_mensaje_servidor(datos)
        except Exception:
            pass
        finally:
            if conexion["socket"] is socket_actual:
                conexion["socket"] = None
                if fase_actual not in ("FIN_PARTIDA",):
                    txt_conexion.value = "🔌 Se perdió la conexión con el servidor/rival."
                    txt_estado.value = "🔌 Conexión perdida."
                    page.update()

    def _procesar_mensaje_servidor(datos):
        nonlocal soy_creador
        tipo = datos.get("tipo")
        if tipo == "sala_creada":
            soy_creador = True
            txt_conexion.value = f"📟 Código de sala: {datos['codigo']}\nCompártelo con tu rival y espera a que se una."
            page.update()
        elif tipo == "union_exitosa":
            soy_creador = False
            txt_conexion.value = "✅ ¡Te uniste a la sala! Esperando a que ambos coloquen sus barcos..."
            page.update()
            _pasar_a_colocacion()
        elif tipo == "rival_conectado":
            txt_conexion.value = "✅ ¡Tu rival se conectó! Ahora coloca tus barcos."
            page.update()
            _pasar_a_colocacion()
        elif tipo == "rival_desconectado":
            txt_estado.value = "⚠️ Tu rival se desconectó de la partida."
            page.update()
        elif tipo == "error":
            txt_conexion.value = f"❌ {datos.get('mensaje', 'Error de conexión')}"
            btn_crear_sala.disabled = False
            btn_unirse_sala.disabled = False
            page.update()
        elif tipo == "mensaje":
            recibir_mensaje_red(datos.get("payload", {}) or {})

    def _pasar_a_colocacion():
        nonlocal fase_actual
        if fase_actual == "CONEXION":
            fase_actual = "COLOCACION"
            panel_conexion.visible = False
            panel_juego.visible = True
            txt_estado.value = "FASE DE ESTRATEGIA: Selecciona un barco y toca tu tablero para colocarlo."
            page.update()

    async def _conectar_y_enviar(accion_inicial):
        try:
            socket_actual = await websockets.connect(DIRECCION_SERVIDOR)
        except Exception:
            txt_conexion.value = "❌ No se pudo conectar al servidor. Revisa la dirección o tu internet."
            btn_crear_sala.disabled = False
            btn_unirse_sala.disabled = False
            page.update()
            return
        conexion["socket"] = socket_actual
        page.run_task(_escuchar_servidor, socket_actual)
        await socket_actual.send(json.dumps(accion_inicial))

    def crear_sala_click(e):
        btn_crear_sala.disabled = True
        btn_unirse_sala.disabled = True
        txt_conexion.value = "Creando sala..."
        page.update()
        page.run_task(_conectar_y_enviar, {"accion": "crear_sala"})

    def unirse_sala_click(e):
        codigo = campo_codigo.value.strip()
        if not codigo:
            txt_conexion.value = "Escribe el código de la sala primero."
            page.update()
            return
        btn_crear_sala.disabled = True
        btn_unirse_sala.disabled = True
        txt_conexion.value = "Conectando..."
        page.update()
        page.run_task(_conectar_y_enviar, {"accion": "unirse_sala", "codigo": codigo})

    def casilla_enemiga_click(e):
        nonlocal mi_turno
        if fase_actual != "BATALLA":
            txt_estado.value = "❌ Espera a que ambos estén listos."
            page.update()
            return
        if not mi_turno:
            txt_estado.value = "⏳ No es tu turno todavía. Espera a que ataque el rival."
            page.update()
            return
        f, c = e.control.data
        if mapa_enemigo[f][c] != 0:
            return
        mi_turno = False  # ya usaste tu turno, ahora espera al rival
        txt_estado.value = "¡Misil enviado! ⏳ Turno del rival."
        page.update()
        enviar_red({"tipo": "ataque", "fila": f, "columna": c})

    def verificar_fin_del_juego():
        nonlocal fase_actual
        mis_aciertos = sum(1 for f in range(TAMANIO_TABLERO) for c in range(TAMANIO_TABLERO) if mapa_enemigo[f][c] == 3)
        aciertos_rival = sum(1 for f in range(TAMANIO_TABLERO) for c in range(TAMANIO_TABLERO) if mi_mapa[f][c] == 3)
        if mis_aciertos >= barcos_totales_enemigo and barcos_totales_enemigo > 0:
            fase_actual = "FIN_PARTIDA"
            txt_estado.value = "¡VICTORIA! 🏆👑"
            txt_estado.color = ft.Colors.YELLOW_400
            page.update()
            return True
        if aciertos_rival >= mis_barcos_totales and mis_barcos_totales > 0:
            fase_actual = "FIN_PARTIDA"
            txt_estado.value = "¡DERROTA! 🏴‍☠️❌"
            txt_estado.color = ft.Colors.RED_400
            page.update()
            return True
        return False

    # --------------------------------------------------
    # CONSTRUCCIÓN DE UN TABLERO CON POSICIONAMIENTO ABSOLUTO
    # --------------------------------------------------
    def construir_tablero(mapa, on_click_fn, mostrar_barcos=False):
        """
        Devuelve una lista de controles para un ft.Stack.
        - Capa 1: celdas individuales posicionadas absolutamente (clickeables)
        - Capa 2: imágenes de barcos estiradas sobre sus celdas (solo tablero propio)
        """
        controles = []

        # — Celdas base —
        for f in range(TAMANIO_TABLERO):
            for c in range(TAMANIO_TABLERO):
                val = mapa[f][c]

                if mostrar_barcos:
                    # Tablero propio: azul marino, o rojo si fue tocado, o azul claro si es agua
                    if val == 3:
                        color = ft.Colors.RED_600
                        icono = ft.Icon(ft.Icons.CLEAR, size=14, color=ft.Colors.WHITE)
                    elif val == 2:
                        color = ft.Colors.BLUE_300
                        icono = ft.Container(width=6, height=6, bgcolor="#FFFFFF", opacity=0.3, border_radius=3)
                    else:
                        color = ft.Colors.BLUE_900
                        icono = None
                else:
                    # Radar enemigo
                    if val == 3:
                        color = ft.Colors.RED_600
                        icono = ft.Icon(ft.Icons.CLEAR, size=14, color=ft.Colors.WHITE)
                    elif val == 2:
                        color = ft.Colors.BLUE_400
                        icono = ft.Container(width=6, height=6, bgcolor="#FFFFFF", opacity=0.3, border_radius=3)
                    else:
                        color = ft.Colors.GREY_800
                        icono = None

                celda = ft.Container(
                    left=c * PASO,
                    top=f * PASO,
                    width=CELDA,
                    height=CELDA,
                    bgcolor=color,
                    border=ft.Border(
                        left=ft.BorderSide(0.5, ft.Colors.BLUE_700 if mostrar_barcos else ft.Colors.GREY_600),
                        right=ft.BorderSide(0.5, ft.Colors.BLUE_700 if mostrar_barcos else ft.Colors.GREY_600),
                        top=ft.BorderSide(0.5, ft.Colors.BLUE_700 if mostrar_barcos else ft.Colors.GREY_600),
                        bottom=ft.BorderSide(0.5, ft.Colors.BLUE_700 if mostrar_barcos else ft.Colors.GREY_600),
                    ),
                    content=icono,
                    on_click=on_click_fn,
                    data=(f, c),
                )
                controles.append(celda)

        # — Imágenes de barcos (solo tablero propio) —
        if mostrar_barcos:
            for barco in mis_barcos_info:
                bf = barco["fila"]
                bc = barco["columna"]
                tam = barco["tamaño"]
                ori = barco["orientacion"]
                nombre = IMAGENES_BARCOS.get(tam, f"barco{tam}.png")

                if not imagen_existe(nombre):
                    continue

                largo = tam * CELDA + (tam - 1) * ESPACIO

                if ori == "V":
                    img_w = CELDA
                    img_h = largo
                else:
                    img_w = largo
                    img_h = CELDA

                img = ft.Container(
                    left=bc * PASO,
                    top=bf * PASO,
                    width=img_w,
                    height=img_h,
                    content=ft.Image(
                        src=nombre,
                        width=img_w,
                        height=img_h,
                        fit="fill",
                    ),
                )
                controles.append(img)

        return controles

    # --------------------------------------------------
    # ACTUALIZACIÓN VISUAL
    # --------------------------------------------------
    def actualizar_pantalla():
        mi_stack.controls = construir_tablero(mi_mapa, mi_casilla_click, mostrar_barcos=True)
        enemigo_stack.controls = construir_tablero(mapa_enemigo, casilla_enemiga_click, mostrar_barcos=False)
        page.update()

    # Inicializar tableros
    actualizar_pantalla()

    # --------------------------------------------------
    # CONTROLES UI
    # --------------------------------------------------
    txt_estado = ft.Text(
        "FASE DE ESTRATEGIA: Selecciona un barco y toca tu tablero para colocarlo.",
        size=14, color=ft.Colors.WHITE,
    )

    contador_text = ft.Text(
        f"🚢 Barcos: 0/{MAX_BARCOS}",
        size=14, color=ft.Colors.YELLOW_400, weight=ft.FontWeight.BOLD,
    )

    botones_barcos = []
    for i in range(1, 5):
        btn = ft.Container(
            content=ft.Column(
                [
                    ft.Text(f"{i}", size=14, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{i} celda{'s' if i > 1 else ''}", size=8, color=ft.Colors.GREY_300),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
            ),
            width=55, height=50,
            bgcolor=ft.Colors.GREEN_800 if i == 1 else ft.Colors.GREY_800,
            border_radius=8,
            border=ft.Border(
                left=ft.BorderSide(2, ft.Colors.GREEN_400 if i == 1 else ft.Colors.GREY_600),
                right=ft.BorderSide(2, ft.Colors.GREEN_400 if i == 1 else ft.Colors.GREY_600),
                top=ft.BorderSide(2, ft.Colors.GREEN_400 if i == 1 else ft.Colors.GREY_600),
                bottom=ft.BorderSide(2, ft.Colors.GREEN_400 if i == 1 else ft.Colors.GREY_600),
            ),
            on_click=seleccionar_barco(i),
            padding=5,
        )
        botones_barcos.append(btn)

    selector_barcos = ft.Row(botones_barcos, alignment=ft.MainAxisAlignment.CENTER, spacing=8)

    btn_orientacion = ft.Container(
        content=ft.Text("↔ HORIZONTAL", size=11, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
        bgcolor=ft.Colors.BLUE_800,
        border_radius=8,
        padding=ft.Padding(left=12, right=12, top=6, bottom=6),
        on_click=cambiar_orientacion,
    )

    def boton_listo_click(e):
        nonlocal fase_actual, mis_barcos_totales, mi_turno
        if fase_actual != "COLOCACION":
            return
        mis_barcos_totales = sum(1 for f in mi_mapa for v in f if v > 0)
        if barcos_colocados == 0:
            txt_estado.value = "⚠️ Debes colocar al menos un barco."
            page.update()
            return
        if rival_listo:
            fase_actual = "BATALLA"
            mi_turno = soy_creador
            txt_estado.value = "🎯 ¡Tu turno! Ataca el radar enemigo." if mi_turno else "⏳ El enemigo ataca primero. Espera tu turno..."
        else:
            fase_actual = "ESPERANDO_RIVAL"
            txt_estado.value = "Flota confirmada. Esperando rival... ⏳"
        btn_listo.bgcolor = ft.Colors.GREEN_700
        btn_listo.disabled = True
        page.update()
        enviar_red({"tipo": "listo", "cantidad_barcos": mis_barcos_totales})

    def limpiar_tablero(e):
        nonlocal mi_mapa, mis_barcos_info, barcos_colocados
        if fase_actual != "COLOCACION":
            return
        mi_mapa = [[0]*TAMANIO_TABLERO for _ in range(TAMANIO_TABLERO)]
        mis_barcos_info = []
        barcos_colocados = 0
        actualizar_contador()
        actualizar_pantalla()
        txt_estado.value = "Tablero limpiado. ¡Vuelve a colocar tus barcos!"
        page.update()

    btn_listo = ft.ElevatedButton(
        content=ft.Row(
            [ft.Icon(ft.Icons.PLAY_ARROW, color=ft.Colors.WHITE),
             ft.Text("¡LISTO PARA LA BATALLA!", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)],
            alignment="center", tight=True,
        ),
        on_click=boton_listo_click,
    )

    btn_limpiar = ft.OutlinedButton(
        content=ft.Row(
            [ft.Icon(ft.Icons.CLEANING_SERVICES, color=ft.Colors.RED_300),
             ft.Text("LIMPIAR TABLERO", color=ft.Colors.RED_300)],
            alignment="center", tight=True,
        ),
        on_click=limpiar_tablero,
    )

    creador = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text("CREADOR", size=18, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            ft.CircleAvatar(foreground_image_src="creador.jpeg", radius=50),
        ]
    )

    # --------------------------------------------------
    # 🔌 PANTALLA DE CONEXIÓN (crear sala / unirse con código)
    # --------------------------------------------------
    campo_codigo = ft.TextField(
        label="Código de sala",
        width=160,
        text_align=ft.TextAlign.CENTER,
        max_length=4,
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    btn_crear_sala = ft.ElevatedButton(
        content=ft.Row(
            [ft.Icon(ft.Icons.ADD_CIRCLE, color=ft.Colors.WHITE),
             ft.Text("CREAR SALA", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)],
            alignment="center", tight=True,
        ),
        on_click=crear_sala_click,
    )
    btn_unirse_sala = ft.ElevatedButton(
        content=ft.Row(
            [ft.Icon(ft.Icons.LOGIN, color=ft.Colors.WHITE),
             ft.Text("UNIRSE", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)],
            alignment="center", tight=True,
        ),
        on_click=unirse_sala_click,
    )
    txt_conexion = ft.Text(
        "Crea una sala nueva, o escribe el código que te compartió tu rival para unirte.",
        size=13, color=ft.Colors.GREY_300, text_align=ft.TextAlign.CENTER,
    )

    panel_conexion = ft.Column(
        [
            ft.Text("GUERRA NAVAL ONLINE", size=28, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            ft.Icon(ft.Icons.SAILING, size=64, color=ft.Colors.BLUE_300),
            ft.Container(height=10),
            txt_conexion,
            ft.Container(height=15),
            btn_crear_sala,
            ft.Container(height=14),
            ft.Text("— o —", size=12, color=ft.Colors.GREY_500),
            ft.Container(height=10),
            ft.Row([campo_codigo, btn_unirse_sala], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=True,
    )

    # --------------------------------------------------
    # MONTAJE DE LA PÁGINA
    # --------------------------------------------------
    panel_juego = ft.Column(
        [
            ft.Text("GUERRA NAVAL ONLINE", size=28, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            txt_estado,
            ft.Container(height=5),
            ft.Row(
                [selector_barcos, ft.Container(width=10), btn_orientacion],
                alignment=ft.MainAxisAlignment.CENTER,
                wrap=True,
            ),
            ft.Container(height=5),
            ft.Row([btn_limpiar, btn_listo], alignment=ft.MainAxisAlignment.CENTER, spacing=10, wrap=True),
            ft.Container(height=5),
            ft.Row([contador_text], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=5),
            # wrap=True: en pantallas angostas (celular) los dos tableros se
            # acomodan uno debajo del otro en vez de cortarse a los costados.
            ft.Row(
                [
                    ft.Column(
                        [ft.Text("DISEÑA TU FLOTA", size=13, color=ft.Colors.GREEN_400, weight=ft.FontWeight.BOLD),
                         mi_stack],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(width=30, height=10),
                    ft.Column(
                        [ft.Text("RADAR ENEMIGO", size=13, color=ft.Colors.RED_400, weight=ft.FontWeight.BOLD),
                         enemigo_stack],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                wrap=True,
            ),
            ft.Container(height=15),
            creador,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False,
    )

    page.add(panel_conexion, panel_juego)

    botones_barcos[0].bgcolor = ft.Colors.GREEN_800
    page.update()


ft.run(main)
