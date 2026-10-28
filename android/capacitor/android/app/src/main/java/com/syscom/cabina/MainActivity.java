package com.syscom.cabina;

import android.graphics.drawable.ColorDrawable;
import android.os.Build;
import android.os.Bundle;
import android.view.WindowManager;

import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.getcapacitor.BridgeActivity;

/**
 * Cabina a pantalla completa.
 *
 * La cabina es un objeto de feria: no hay barra de estado que consultar ni
 * gestos que descubrir. Sin ocultar las barras del sistema quedaban dos franjas
 * grises arriba y abajo y el escenario parecia una web metida en una ventana.
 */
public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // El fondo de la ventana tapa el ratito previo al primer pintado; si se
        // deja el que trae el tema se ve un flash gris al abrir.
        getWindow().setBackgroundDrawable(new ColorDrawable(0xFF070F20));

        // Acostado, el agujero de la camara frontal queda en un borde. Android,
        // por defecto, encoge el dibujo para no taparlo y deja una banda gris de
        // 88 px a un lado. Con shortEdges el escenario llega hasta el borde.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            getWindow().getAttributes().layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
        }

        super.onCreate(savedInstanceState);

        // La pagina se dibuja tambien debajo de donde irian las barras.
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);

        WindowInsetsControllerCompat controller =
                WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());

        // Se ocultan, pero no para siempre: un deslizamiento desde el borde las
        // devuelve un momento, que es lo que hace falta si hay que salir de la app.
        controller.hide(WindowInsetsCompat.Type.systemBars());
        controller.setSystemBarsBehavior(
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        // Al volver de otra app (o de una barra desplegada) el sistema las
        // restaura; se ocultan otra vez.
        if (hasFocus) {
            WindowInsetsControllerCompat controller =
                    WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
            controller.hide(WindowInsetsCompat.Type.systemBars());
        }
    }
}
