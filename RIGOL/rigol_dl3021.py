from chroma_pyvisa import ChromaPyVISA
from time import sleep

# Definicion de mi funcion.
def mi_funcion():
    try:
        resource_name = "USB0::0x1AB1::0x0E11::DL3A243500940::INSTR"
        # Modo de corriente constante.
        corriente = 2.5
        corrientes = [0.5, 1.0, 1.5, 2.0, 2.5]
        

        # Instancio mi objeto "carga".
        carga = ChromaPyVISA() #ChromaRS232()

        # Comunicacion
        if not resource_name:
            resource_name = carga.get_resource_name_chosen_by_user()
        
        if not resource_name:
            print("Nombre de recurso no valido.")
            return False
        
        carga.resource_name = resource_name

        # Conectar a la carga.
        if not carga.connect():
            print("No se pudo conectar a la carga.")
            return False
        
        # Apagar la carga.
        carga.write("INP OFF")

        respuesta = carga.query("INP?")

        if respuesta != "0":
            carga.logger.error("No se pudo apagar la carga.")
            return False

        carga.logger.debug("Carga apagada.")

        respuesta = carga.query("SYST:ERR?")

        # Modo de corriente constante.
        carga.write(":FUNC CURR")

        respuesta = carga.query(":FUNC?")
        carga.logger.debug("El modo de carga es: %s", respuesta)

        # Preguntar el slew rate de la corriente.
        respuesta = carga.query("SOURCE:CURRENT:SLEW?")
        carga.logger.debug("Slew Rate: %s", respuesta)

        respuesta = carga.query(":SOURCE:CURRENT:SLEW? MAX")

        # [:SOURce]CURRent:SLEW x

        '''
        # Especificar la corriente para el modo de CC.
        carga.write(":CURR %s" % (corriente))

        respuesta = carga.query(":CURR?")
        # Verificar que la corriente es un numero flotante.
        if carga.is_float(respuesta):
            corriente_configurada = float(respuesta)
            carga.logger.debug("La carga configurada es: %s", corriente_configurada)
        else:
            carga.logger.error("La corriente no es un numero flotante.")
            return False
        '''

        carga.write("INPUT ON")
        
        for i in range(0, len(corrientes), 1):
            carga.write(":CURR %s" % corrientes[i])
            sleep(1)

            voltage = carga.query("MEAS:VOLT?")
            corriente = carga.query("MEAS:CURR?")
            potencia = carga.query("MEAS:POW?")
            capacidad = carga.query("MEAS:CAP?")
            carga.logger.debug("V = %s | I = %s | W = %s | C = %s",
                               voltage, corriente, potencia, capacidad)
            
            respuesta = carga.query(":MEAS:VOLT?;CURR?;POW?")
            carga.logger.debug("VIP: %s", respuesta)

            respuesta = input("Presiona una tecla para continuar.")

        carga.write("INPUT OFF")
        respuesta = carga.query("INPUT?")
        if respuesta != "0":
            carga.logger.debug("ADVERTENCIA: No se pudo apagar la entrada de la carga.")

        '''
        continuar = True
        while(continuar):
            respuesta = input("Presiona la tecla <S> para continuar.")
            if respuesta.upper() != "S":
                continuar = False
        '''

        
        return True
    except Exception as ex:
        print("Ocurrio una excepcion: %s" % (str(ex)))
        return False
    
# Ejecuto mi funcion.
mi_funcion()